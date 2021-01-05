#!/usr/bin/env python3

import sys, logging, struct, collections, io
import numpy
import matplotlib.pyplot as plt

from soapypower import threadpool

if sys.platform == 'win32':
    import msvcrt

logger = logging.getLogger(__name__)


class BaseWriter:
    """Power Spectral Density writer base class"""
    def __init__(self, output=sys.stdout):
        self._close_output = False

        # If output is integer, assume it is file descriptor and open it
        if isinstance(output, int):
            self._close_output = True
            if sys.platform == 'win32':
                output = msvcrt.open_osfhandle(output, 0)
            output = open(output, 'wb')

        # Get underlying buffered file object
        try:
            self.output = output.buffer
        except AttributeError:
            self.output = output

        # Use only one writer thread to preserve sequence of written frequencies
        self._executor = threadpool.ThreadPoolExecutor(
            max_workers=1,
            max_queue_size=100,
            thread_name_prefix='Writer_thread'
        )

    def write(self, psd_data_or_future, time_start, time_stop, samples):
        """Write PSD of one frequency hop"""
        raise NotImplementedError

    def write_async(self, psd_data_or_future, time_start, time_stop, samples, signal, threshold, server, port):
        """Write PSD of one frequncy hop (asynchronously in another thread)"""
        return self._executor.submit(self.write, psd_data_or_future, time_start, time_stop, samples, signal, threshold, server, port)

    def write_next(self):
        """Write marker for next run of measurement"""
        raise NotImplementedError

    def write_next_async(self):
        """Write marker for next run of measurement (asynchronously in another thread)"""
        return self._executor.submit(self.write_next)

    def close(self):
        """Close output (only if it has been opened by writer)"""
        if self._close_output:
            self.output.close()


class SoapyPowerBinFormat:
    """Power Spectral Density binary file format"""
    header_struct = struct.Struct('<BdddddQQ2x')
    header = collections.namedtuple('Header', 'version time_start time_stop start stop step samples size')
    magic = b'SDRFF'
    version = 2

    def read(self, f):
        """Read data from file-like object"""
        magic = f.read(len(self.magic))
        if not magic:
            return None
        if magic != self.magic:
            raise ValueError('Magic bytes not found! Read data: {}'.format(magic))

        header = self.header._make(
            self.header_struct.unpack(f.read(self.header_struct.size))
        )
        pwr_array = numpy.fromstring(f.read(header.size), dtype='float32')
        return (header, pwr_array)

    def write(self, f, time_start, time_stop, start, stop, step, samples, pwr_array):
        """Write data to file-like object"""
        f.write(self.magic)
        f.write(self.header_struct.pack(
            self.version, time_start, time_stop, start, stop, step, samples, pwr_array.nbytes
        ))
        #pwr_array.tofile(f)
        f.write(pwr_array.tobytes())
        f.flush()

    def header_size(self):
        """Return total size of header"""
        return len(self.magic) + self.header_struct.size


class SoapyPowerBinWriter(BaseWriter):
    """Write Power Spectral Density to stdout or file (in soapy_power binary format)"""
    def __init__(self, output=sys.stdout):
        super().__init__(output=output)
        self.formatter = SoapyPowerBinFormat()

    def write(self, psd_data_or_future, time_start, time_stop, samples):
        """Write PSD of one frequency hop"""
        try:
            # Wait for result of future
            f_array, pwr_array = psd_data_or_future.result()
        except AttributeError:
            f_array, pwr_array = psd_data_or_future

        try:
            step = f_array[1] - f_array[0]
            self.formatter.write(
                self.output,
                time_start.timestamp(),
                time_stop.timestamp(),
                f_array[0],
                f_array[-1] + step,
                step,
                samples,
                pwr_array
            )
        except Exception as e:
            logging.exception('Error writing to output file: {}'.format(e))

    def write_next(self):
        """Write marker for next run of measurement"""
        pass


class RtlPowerFftwWriter(BaseWriter):
    """Write Power Spectral Density to stdout or file (in rtl_power_fftw format)"""
    def __init__(self, output=sys.stdout):
        super().__init__(output=output)
        self.output = io.TextIOWrapper(self.output)

    def write(self, psd_data_or_future, time_start, time_stop, samples):
        """Write PSD of one frequency hop"""
        try:
            # Wait for result of future
            f_array, pwr_array = psd_data_or_future.result()
        except AttributeError:
            f_array, pwr_array = psd_data_or_future

        self.output.write('# soapy_power output\n')
        self.output.write('# Acquisition start: {}\n'.format(time_start))
        self.output.write('# Acquisition end: {}\n'.format(time_stop))
        self.output.write('#\n')
        self.output.write('# frequency [Hz] power spectral density [dB/Hz]\n')

        for f, pwr in zip(f_array, pwr_array):
            self.output.write('{} {}\n'.format(f, pwr))

        self.output.write('\n')
        self.output.flush()

    def write_next(self):
        """Write marker for next run of measurement"""
        self.output.write('\n')
        self.output.flush()


class RtlPowerWriter(BaseWriter):
    """Write Power Spectral Density to stdout or file (in rtl_power format)"""
    def __init__(self, output=sys.stdout):
        super().__init__(output=output)
        self.output = io.TextIOWrapper(self.output)

    def write(self, psd_data_or_future, time_start, time_stop, samples, signal, threshold, server, port):
        """Write PSD of one frequency hop"""
        try:
            # Wait for result of future
            f_array, pwr_array = psd_data_or_future.result()
        except AttributeError:
            f_array, pwr_array = psd_data_or_future
        try:
            #step = f_array[1] - f_array[0]
            #row = [
            #    time_stop.strftime('%Y-%m-%d'), time_stop.strftime('%H:%M:%S'),
            #    f_array[0], f_array[-1] + step, step, samples
            #]
            #row += list(pwr_array)
            #self.output.write('{}\n'.format(', '.join(str(x) for x in row)))

            # FD measurements
            peak = numpy.argmax(pwr_array)
            signal["rssi"] = pwr_array[peak]

            if signal["rssi"] < threshold:
              return
            # Measure bandwidth at -3dB point
            halfPower = signal["rssi"]-3
            leftEdge = peak
            rightEdge = peak
            edges = numpy.where(pwr_array > halfPower)[0]

            leftEdge = edges[0]
            rightEdge = edges[-1]
            # <<<<<<<<<<<<<<
            #while leftEdge > 0:
            #  if pwr_array[leftEdge] < halfPower:
            #    break
            #  leftEdge-=1
            # >>>>>>>>>>>>>>
            #while rightEdge < len(pwr_array):
            #  if pwr_array[rightEdge] < halfPower:
            #    break
            #  rightEdge+=1




            # Bandwidth in Hz per FFT bin for precise freq measurements
            resolution = signal["rate"] / len(pwr_array)

            signal["bandwidth"] = resolution * (rightEdge-leftEdge)

            # Take mean as centre frequency for flat top signals
            midpoint = len(pwr_array)/2
            centreFreq = (leftEdge+rightEdge)/2
            if centreFreq <= midpoint:
              offset = (resolution * (midpoint-centreFreq)) * -1
            else:
              offset = resolution * (centreFreq-midpoint)

            # update frequency
            signal["freq"] += offset
            # Plot a signal :)
            filename = "%s_%.03fMHz_%.06fs_%dKHz_%.01fdBm" % (signal["reportTime"],signal["freq"]/1e6,signal["duration"],signal["bandwidth"]/1e3,signal["rssi"])
            self.output.write(filename+"\n")
            self.output.flush()

            #fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10,5))
            #fig.suptitle(filename)
            #ax1.plot(signal["td_array"])
            #ax2.plot(pwr_array)
            #plt.savefig(filename)
            #plt.show()
            
        except Exception as e:
            logging.exception('Error writing to output file:')

    def write_next(self):
        """Write marker for next run of measurement"""
        pass


formats = {
    'soapy_power_bin': SoapyPowerBinWriter,
    'rtl_power_fftw': RtlPowerFftwWriter,
    'rtl_power': RtlPowerWriter,
}
