#!/usr/bin/env python3

import sys, time, datetime, math, logging, signal

import numpy
import simplesoapy
from simplespectral import zeros
from soapypower import psd, writer
import socket
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)
_shutdown = False


def _shutdown_handler(sig, frame):
    """Set global _shutdown flag when receiving SIGTERM or SIGINT signals"""
    global _shutdown
    _shutdown = True


# Register signals with _shutdown_handler
signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)

if sys.platform == 'win32':
    signal.signal(signal.SIGBREAK, _shutdown_handler)


class SoapyPower:
    """SoapySDR spectrum analyzer"""
    def __init__(self, soapy_args='', sample_rate=2.00e6, bandwidth=0, corr=0, gain=20.7,
                 auto_gain=False, channel=0, antenna='', settings=None,
                 force_sample_rate=False, force_bandwidth=False,
                 output=sys.stdout, output_format='rtl_power', threshold=-85, server='127.0.0.1', port=2048, plot=0):
        self.device = simplesoapy.SoapyDevice(
            soapy_args=soapy_args, sample_rate=sample_rate, bandwidth=bandwidth, corr=corr,
            gain=gain, auto_gain=auto_gain, channel=channel, antenna=antenna, settings=settings,
            force_sample_rate=force_sample_rate, force_bandwidth=force_bandwidth
        )

        # simplesoapy uses SOAPY_SDR_CF32 (2^31) :/
        self.scale = 2 ** 31 # 2^7=128, 2^15=32768, 2^31=2147483648
        self._output = output
        self._output_format = output_format
        self.threshold = threshold
        self.server = server
        self.port = port
        self._buffer = None
        self._buffer_repeats = None
        self._base_buffer_size = None
        self._max_buffer_size = None
        self._bins = None
        self._repeats = None
        self._tune_delay = None
        self._reset_stream = None
        self._psd = None
        self._writer = None
        self.sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.count = 0
        self.plotting = plot

    def nearest_freq(self, freq, bin_size):
        """Return nearest frequency based on bin size"""
        return round(freq / bin_size) * bin_size

    def nearest_bins(self, bins, even=False, pow2=False):
        """Return nearest number of FFT bins (even or power of two)"""
        if pow2:
            bins_log2 = math.log(bins, 2)
            if bins_log2 % 1 != 0:
                bins = 2**math.ceil(bins_log2)
                logger.warning('number of FFT bins should be power of two, changing to {}'.format(bins))
        elif even:
            if bins % 2 != 0:
                bins = math.ceil(bins / 2) * 2
                logger.warning('number of FFT bins should be even, changing to {}'.format(bins))

        return bins

    def nearest_overlap(self, overlap, bins):
        """Return nearest overlap/crop factor based on number of bins"""
        bins_overlap = overlap * bins
        if bins_overlap % 2 != 0:
            bins_overlap = math.ceil(bins_overlap / 2) * 2
            overlap = bins_overlap / bins
            logger.warning('number of overlapping FFT bins should be even, '
                           'changing overlap/crop factor to {:.5f}'.format(overlap))
        return overlap

    def bin_size_to_bins(self, bin_size):
        """Convert bin size [Hz] to number of FFT bins"""
        return math.ceil(self.device.sample_rate / bin_size)

    def bins_to_bin_size(self, bins):
        """Convert number of FFT bins to bin size [Hz]"""
        return self.device.sample_rate / bins

    def time_to_repeats(self, bins, integration_time):
        """Convert integration time to number of repeats"""
        return math.ceil((self.device.sample_rate * integration_time) / bins)

    def repeats_to_time(self, bins, repeats):
        """Convert number of repeats to integration time"""
        return (repeats * bins) / self.device.sample_rate

    def freq_plan(self, min_freq, max_freq, bins, overlap=0, quiet=False):
        """Returns list of frequencies for frequency hopping"""
        bin_size = self.bins_to_bin_size(bins)
        bins_crop = round((1 - overlap) * bins)
        sample_rate_crop = (1 - overlap) * self.device.sample_rate

        freq_range = max_freq - min_freq
        hopping = True if freq_range >= sample_rate_crop else False
        hop_size = self.nearest_freq(sample_rate_crop, bin_size)
        hops = math.ceil(freq_range / hop_size) if hopping else 1
        min_center_freq = min_freq + (hop_size / 2) if hopping else min_freq + (freq_range / 2)
        max_center_freq = min_center_freq + ((hops - 1) * hop_size)

        freq_list = [min_center_freq + (i * hop_size) for i in range(hops)]

        if not quiet:
            logger.info('overlap: {:.5f}'.format(overlap))
            logger.info('bin_size: {:.2f} Hz'.format(bin_size))
            logger.info('bins: {}'.format(bins))
            logger.info('bins (after crop): {}'.format(bins_crop))
            logger.info('sample_rate: {:.3f} MHz'.format(self.device.sample_rate / 1e6))
            logger.info('sample_rate (after crop): {:.3f} MHz'.format(sample_rate_crop / 1e6))
            logger.info('freq_range: {:.3f} MHz'.format(freq_range / 1e6))
            logger.info('hopping: {}'.format('YES' if hopping else 'NO'))
            logger.info('hop_size: {:.3f} MHz'.format(hop_size / 1e6))
            logger.info('hops: {}'.format(hops))
            logger.info('min_center_freq: {:.3f} MHz'.format(min_center_freq / 1e6))
            logger.info('max_center_freq: {:.3f} MHz'.format(max_center_freq / 1e6))
            logger.info('min_freq (after crop): {:.3f} MHz'.format((min_center_freq - (hop_size / 2)) / 1e6))
            logger.info('max_freq (after crop): {:.3f} MHz'.format((max_center_freq + (hop_size / 2)) / 1e6))
            logger.info('threshold: {:.1f} dBm'.format(self.threshold))
            logger.info('threshold abs: {}'.format((10 ** (self.threshold/10))* self.scale))
            logger.info('server: {} '.format(self.server))
            logger.info('port: {} '.format(self.port))
            logger.debug('Frequency hops table:')
            logger.debug('  {:8s}      {:8s}      {:8s}'.format('Min:', 'Center:', 'Max:'))
            for f in freq_list:
                logger.debug('  {:8.3f} MHz  {:8.3f} MHz  {:8.3f} MHz'.format(
                    (f - (self.device.sample_rate / 2)) / 1e6,
                    f / 1e6,
                    (f + (self.device.sample_rate / 2)) / 1e6,
                ))

        return freq_list

    def create_buffer(self, bins, repeats, base_buffer_size, max_buffer_size=0):
        """Create buffer for reading samples"""
        samples = bins * repeats
        buffer_repeats = 1
        buffer_size = math.ceil(samples / base_buffer_size) * base_buffer_size

        if not max_buffer_size:
            # Max buffer size about 100 MB
            max_buffer_size = (100 * 1024**2) / 8

        if max_buffer_size > 0:
            max_buffer_size = math.ceil(max_buffer_size / base_buffer_size) * base_buffer_size
            if buffer_size > max_buffer_size:
                logger.warning('Required buffer size ({}) will be shrinked to max_buffer_size ({})!'.format(
                    buffer_size, max_buffer_size
                ))
                buffer_repeats = math.ceil(buffer_size / max_buffer_size)
                buffer_size = max_buffer_size

        logger.info('repeats: {}'.format(repeats))
        logger.info('samples: {} (time: {:.5f} s)'.format(samples, samples / self.device.sample_rate))
        if max_buffer_size > 0:
            logger.info('max_buffer_size (samples): {} (repeats: {:.2f}, time: {:.5f} s)'.format(
                max_buffer_size, max_buffer_size / bins, max_buffer_size / self.device.sample_rate
            ))
        else:
            logger.info('max_buffer_size (samples): UNLIMITED')
        logger.info('buffer_size (samples): {} (repeats: {:.2f}, time: {:.5f} s)'.format(
            buffer_size, buffer_size / bins, buffer_size / self.device.sample_rate
        ))
        logger.info('buffer_repeats: {}'.format(buffer_repeats))

        return (buffer_repeats, zeros(buffer_size, numpy.complex64))

    def setup(self, bins, repeats, base_buffer_size=0, max_buffer_size=0, fft_window='hann',
              fft_overlap=0.5, crop_factor=0, log_scale=True, remove_dc=False, detrend=None,
              lnb_lo=0, tune_delay=0, reset_stream=False, max_threads=0, max_queue_size=0):
        """Prepare samples buffer and start streaming samples from device"""
        if self.device.is_streaming:
            self.device.stop_stream()

        base_buffer = self.device.start_stream(buffer_size=base_buffer_size)
        self._bins = bins
        self._repeats = repeats
        self._base_buffer_size = len(base_buffer)
        self._max_buffer_size = max_buffer_size
        self._buffer_repeats, self._buffer = self.create_buffer(
            bins, repeats, self._base_buffer_size, self._max_buffer_size
        )
        self._tune_delay = tune_delay
        self._reset_stream = reset_stream
        self._psd = psd.PSD(bins, self.device.sample_rate, fft_window=fft_window, fft_overlap=fft_overlap,
                            crop_factor=crop_factor, log_scale=log_scale, remove_dc=remove_dc, detrend=detrend,
                            lnb_lo=lnb_lo, max_threads=max_threads, max_queue_size=max_queue_size)
        self._writer = writer.formats[self._output_format](self._output)

    def stop(self):
        """Stop streaming samples from device and delete samples buffer"""
        if not self.device.is_streaming:
            return

        self.device.stop_stream()
        self._writer.close()

        self._bins = None
        self._repeats = None
        self._base_buffer_size = None
        self._max_buffer_size = None
        self._buffer_repeats = None
        self._buffer = None
        self._tune_delay = None
        self._reset_stream = None
        self._psd = None
        self._writer = None

    def psd(self, freq):
        """Tune to specified center frequency and compute Power Spectral Density"""
        if not self.device.is_streaming:
            raise RuntimeError('Streaming is not initialized, you must run setup() first!')

        # Tune to new frequency in main thread
        logger.debug('  Frequency hop: {:.2f} Hz'.format(freq))
        t_freq = time.time()
        signal = {"start": -1, "stop": 0, "samples": 0, "duration": 0}
        if self.device.freq != freq:
            # Deactivate streaming before tuning
            if self._reset_stream:
                self.device.device.deactivateStream(self.device.stream)

            # Actually tune to new center frequency
            self.device.freq = freq

            # Reactivate streaming after tuning
            if self._reset_stream:
                self.device.device.activateStream(self.device.stream)

            # Delay reading samples after tuning
            if self._tune_delay:
                t_delay = time.time()
                while True:
                    self.device.read_stream()
                    t_delay_end = time.time()
                    if t_delay_end - t_delay >= self._tune_delay:
                        break
                logger.debug('    Tune delay: {:.6f} s'.format(t_delay_end - t_delay))
        else:
            logger.debug('    Same frequency as before, tuning skipped')
        psd_state = self._psd.set_center_freq(freq)
        t_freq_end = time.time()
        logger.debug('    Tune time: {:.6f} s'.format(t_freq_end - t_freq))

        # Only interested in bursts of power > 5us
        minBurst = int(0.000005 * self.device.sample_rate)

        # initial threshold...
        absThreshold = (10 ** (self.threshold/10)) * self.scale

        for repeat in range(self._buffer_repeats):
            logger.debug('    Repeat: {}'.format(repeat + 1))
            # Read samples from SDR in main thread
            t_acq = time.time()

            acq_time_start = datetime.datetime.utcnow() # not accurate.
            self.device.read_stream_into_buffer(self._buffer)

            acq_time_stop = datetime.datetime.utcnow()
            t_acq_end = time.time()
            logger.debug('      Acquisition time: {:.6f} s'.format(t_acq_end - t_acq))
	
            iq = self._buffer.real+self._buffer.imag
 
            # dynamic threshold
            noise = abs(numpy.mean(iq[:100]))
            if noise < absThreshold:
              absThreshold = noise * 100
              #print("Threshold set to %.4f" % absThreshold)

            # Only interested in processing power
            if numpy.max(iq) > absThreshold:
              
              # Array of power values which exceed absThreshold
              burst = numpy.where(numpy.abs(iq) > absThreshold)[0]

              #print(absThreshold,len(burst))
              # Start power is easy :)
              start = burst[0]

              # Stop is trickier :p
              # Search burst for the last value above the absThreshold which must be followed by a gap of minBurst samples to be sure.
              delta=0
              laststop=start
              for stop in burst:
                delta=stop-laststop
                if delta > minBurst:
                  stop = laststop
                  break
                laststop=stop
              
              if stop-start > minBurst:  
                safestart=0
                safestop = len(iq) -1
                if start > minBurst:
                    safestart = start-minBurst
                if safestop-stop > minBurst:
                    safestop = stop+minBurst

                signal["freq"] = freq
                signal["start"] = start
                signal["stop"] = stop
                signal["samples"] = stop-start
                signal["duration"] = ((stop-start)/self.device.sample_rate)
                signal["td_array"] = numpy.abs(iq[safestart:safestop])
                signal["reportTime"] = acq_time_start
                signal["rate"] = self.device.sample_rate

                # Start FFT computation in another thread
                self._psd.update_async(psd_state, numpy.copy(self._buffer[start:stop]))

            t_final = time.time()

            if _shutdown:
                break

        psd_future = self._psd.result_async(psd_state)
        logger.debug('    Total hop time: {:.6f} s'.format(t_final - t_freq))

        return (psd_future, acq_time_start, acq_time_stop, signal)

    def sweep(self, min_freq, max_freq, bins, repeats, runs=0, time_limit=0, overlap=0,
              fft_window='hann', fft_overlap=0.5, crop=False, log_scale=True, remove_dc=False, detrend=None, lnb_lo=0,
              tune_delay=0, reset_stream=False, base_buffer_size=0, max_buffer_size=0, max_threads=0, max_queue_size=0):
        """Sweep spectrum using frequency hopping"""
        self.setup(
            bins, repeats, base_buffer_size, max_buffer_size,
            fft_window=fft_window, fft_overlap=fft_overlap, crop_factor=overlap if crop else 0,
            log_scale=log_scale, remove_dc=remove_dc, detrend=detrend, lnb_lo=lnb_lo, tune_delay=tune_delay,
            reset_stream=reset_stream, max_threads=max_threads, max_queue_size=max_queue_size
        )

        try:
            freq_list = self.freq_plan(min_freq - lnb_lo, max_freq - lnb_lo, bins, overlap)
            t_start = time.time()
            run = 0
            while not _shutdown and (runs == 0 or run < runs):
                run += 1
                t_run_start = time.time()
                logger.debug('Run: {}'.format(run))

                for freq in freq_list:
                    # Tune to new frequency, acquire samples and compute Power Spectral Density
                    psd_future, acq_time_start, acq_time_stop, signal = self.psd(freq)

                    if signal["start"] > -1:
                      json = self.measurements(psd_future, len(self._buffer) * self._buffer_repeats, signal)
                      if json:
                        self.sock.sendto(json.encode('utf-8'), (self.server, self.port))
                        print(self.count,json)
                        self.count +=1 
                    if _shutdown:
                        break

                # Write end of measurement marker (in another thread)
                #write_next_future = self._writer.write_next_async()
                t_run = time.time()
                logger.debug('  Total run time: {:.3f} s'.format(t_run - t_run_start))

                # End measurement if time limit is exceeded
                if time_limit and (time.time() - t_start) >= time_limit:
                    logger.info('Time limit of {} s exceeded, completed {} runs'.format(time_limit, run))
                    break

            # Wait for last write to be finished
            #write_next_future.result()

            # Debug thread pool queues
            logging.debug('Number of USB buffer overflow errors: {}'.format(self.device.buffer_overflow_count))
            logging.debug('PSD worker threads: {}'.format(self._psd._executor._max_workers))
            logging.debug('Max. PSD queue size: {} / {}'.format(self._psd._executor.max_queue_size_reached,
                                                                self._psd._executor.max_queue_size))
            logging.debug('Writer worker threads: {}'.format(self._writer._executor._max_workers))
            logging.debug('Max. Writer queue size: {} / {}'.format(self._writer._executor.max_queue_size_reached,
                                                                   self._writer._executor.max_queue_size))
        finally:
            # Shutdown SDR
            self.stop()
            t_stop = time.time()
            logger.info('Total time: {:.3f} s'.format(t_stop - t_start))

    def measurements(self, psd_data_or_future, samples, signal):

        try:
            f_array, pwr_array = psd_data_or_future.result()
        except AttributeError:
            f_array, pwr_array = psd_data_or_future

        # FD measurements
        try:
          peak = numpy.argmax(pwr_array)
          signal["rssi"] = pwr_array[peak]
        except:
          print("pwr_array not empty")
          return

        if signal["rssi"] < self.threshold:
          #print("Signal too low at %ddBm" % signal["rssi"])
          return

        # Measure bandwidth at -3dB point
        halfPower = signal["rssi"]-3
        leftEdge = peak
        rightEdge = peak
        edges = numpy.where(pwr_array > halfPower)[0]
        leftEdge = edges[0]
        rightEdge = edges[-1]

        # Bandwidth in Hz per FFT bin for precise freq measurements
        resolution = signal["rate"] / len(pwr_array)

        # FFT parameters for reading PSD
        leftFreq = signal["freq"] - (self.device.sample_rate/2)
        rightFreq = signal["freq"] + (self.device.sample_rate/2)

        signal["bandwidth"] = resolution * (rightEdge-leftEdge)

        # Take mean as centre frequency for flat top signals
        midpoint = len(pwr_array)/2
        centreFreq = (leftEdge+rightEdge)/2
        if centreFreq <= midpoint:
          offset = (resolution * (midpoint-centreFreq)) * -1
        else:
          offset = resolution * (centreFreq-midpoint)

        # focused PSD on signal only pwr_array[leftEdge:rightEdge]
        psd = numpy.int_(numpy.array(pwr_array))
        psd = (','.join(str(int(v)) for v in psd))


        # update frequency
        signal["freq"] += offset
        json = '{\n "reportTime": "%s",\n "frequencyMHz": %.3f,\n "bandwidthKHz": %d,\n "psd": [%s],\n "spanMHz": [%.3f,%.3f], \n "durationMs": %.3f,\n "rssidBm": %.1f\n}\n' % (signal["reportTime"],signal["freq"]/1e6,signal["bandwidth"]/1e3,psd,leftFreq/1e6,rightFreq/1e6,signal["duration"]*1e3,signal["rssi"])

        if self.plotting:
          fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10,5))
          fig.suptitle("F "+str(round(signal["freq"]/1e6,3))+"MHz W "+str(round(signal["bandwidth"]/1e3))+"KHz D "+str(round(signal["duration"]*1e3,3))+"ms")
          ax1.plot(signal["td_array"])
          ax2.plot(pwr_array)
          plt.savefig("/tmp/"+str(signal["reportTime"])+".png")
          plt.close()
        
        return json            
