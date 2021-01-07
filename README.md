soapy_power
===========

Detect and measure signals remotely with SoapySDR devices (RTL-SDR, Airspy, SDRplay, HackRF, bladeRF, USRP, LimeSDR, etc.)

Outputs JSON messages via UDP 127.0.0.1:2048 and plots signal time domain and frequency domain to /tmp. Each message is structured as follows:

 - reportTime: ISO-8601 timestmap (host clock) at the point I/Q capture was started. 
 - frequencyMHz: Peak signal frequency measured in megahertz
 - bandwidthKHz: Signal bandwidth as measured at -3dB point
 - psd: Power spectral display (FFT) values as dBm
 - spanMHz: PSD left edge frequency, PSD right edge frequency in megahertz
 - durationMs: Signal duration in milliseconds to 3 decimal places
 - rssidBm: Peak signal power measured in dBm

Output can be networked to a server via the --host and --port arguments.

Client

	soapy_power -r 16M -f 2400M:2480M -g 45 -d driver=uhd -b 128 -t 0.01 --threshold -100 -c -o 50

Server
	
	nc -v -u -l -p 2048
	Listening on [0.0.0.0] (family 0, port 2048)
	Connection from localhost 52478 received!
	{
	 "reportTime": "2021-01-07 11:59:01.579568",
	 "frequencyMHz": 2480.000,
	 "bandwidthKHz": 500,
	 "psd": [-120,-119,-119,-118,-118,-117,-117,-117,-116,-116,-116,-116,-116,-117,-116,-115,-115,-115,-116,-116,-115,-115,-116,-115,-116,-116,-115,-115,-116,-116,-115,-115,-115,-115,-115,-115,-115,-115,-115,-115,-116,-115,-115,-115,-115,-115,-115,-115,-116,-115,-115,-116,-116,-116,-115,-115,-116,-115,-116,-116,-115,-115,-115,-115,-115,-115,-115,-115,-115,-115,-115,-115,-115,-115,-115,-115,-116,-116,-115,-115,-115,-115,-116,-116,-115,-115,-115,-115,-113,-112,-110,-101,-93,-88,-85,-84,-84,-85,-86,-90,-95,-102,-111,-113,-113,-115,-116,-116,-116,-116,-116,-116,-116,-117,-117,-117,-116,-117,-117,-117,-118,-117,-117,-117,-118,-118,-119,-120],
	 "spanMHz": [2468.000,2484.000], 
	 "durationMs": 0.390,
	 "rssidBm": -84.6
	}
	{
	 "reportTime": "2021-01-07 11:59:02.102782",
	 "frequencyMHz": 2416.438,
	 "bandwidthKHz": 2125,
	 "psd": [-109,-110,-111,-115,-116,-116,-116,-116,-117,-118,-117,-117,-117,-116,-116,-117,-117,-117,-115,-116,-116,-116,-116,-115,-115,-116,-115,-115,-115,-115,-116,-115,-115,-117,-118,-116,-116,-116,-115,-115,-116,-115,-115,-114,-114,-115,-115,-115,-115,-116,-115,-115,-114,-113,-114,-114,-113,-112,-112,-110,-108,-103,-97,-95,-96,-95,-95,-96,-94,-96,-98,-98,-99,-99,-100,-102,-102,-103,-104,-103,-101,-101,-100,-98,-98,-96,-97,-96,-93,-94,-94,-93,-93,-92,-93,-92,-91,-92,-90,-91,-92,-92,-93,-91,-93,-93,-94,-94,-93,-94,-95,-96,-98,-99,-100,-101,-103,-105,-106,-106,-105,-105,-104,-102,-101,-99,-101,-105],
	 "spanMHz": [2404.000,2420.000], 
	 "durationMs": 0.155,
	 "rssidBm": -90.9
	}


Requirements
------------

- `Python 3 <https://www.python.org>`_
- `NumPy <http://www.numpy.org>`_
- `SimpleSoapy <https://github.com/xmikos/simplesoapy>`_
- `SimpleSpectral <https://github.com/xmikos/simplespectral>`_
- Optional: `pyFFTW <https://github.com/pyFFTW/pyFFTW>`_ (for fastest FFT calculations with FFTW library)
- Optional: `SciPy <https://www.scipy.org>`_ (for faster FFT calculations with scipy.fftpack library)

You should always install SciPy or pyFFTW, because numpy.fft has horrible
memory usage and is also much slower.

Usage
-----
	usage: soapy_power [-h] [-f Hz|Hz:Hz] [-O FILE | --output-fd NUM] [-F {rtl_power,rtl_power_fftw,soapy_power_bin}] [-q] [--debug] [--detect]
		           [--info] [--version] [-b BINS | -B Hz] [-n REPEATS | -t SECONDS | -T SECONDS] [-c | -u RUNS | -e SECONDS] [-d DEVICE]
		           [-C CHANNEL] [-A ANTENNA] [-r Hz] [-w Hz] [-p PPM] [-g dB | -G STRING | -a] [--lnb-lo Hz] [--device-settings STRING]
		           [--force-rate] [--force-bandwidth] [--tune-delay SECONDS] [--reset-stream] [-o PERCENT | -k PERCENT] [-s BUFFER_SIZE]
		           [-S MAX_BUFFER_SIZE] [--even | --pow2] [--max-threads NUM] [--max-queue-size NUM] [--no-pyfftw] [-l] [-R]
		           [-D {none,constant}] [--fft-window {boxcar,hann,hamming,blackman,bartlett,kaiser,tukey}] [--fft-window-param FLOAT]
		           [--fft-overlap PERCENT] [--threshold FLOAT] [--server SERVER] [--port PORT] [--plot PLOT]

	Detect and measure signals with SoapySDR devices

	Main options:
	  -h, --help            show this help message and exit
	  -f Hz|Hz:Hz, --freq Hz|Hz:Hz
		                center frequency or frequency range to scan, number can be followed by a k, M or G multiplier (default: 1420405752)
	  -O FILE, --output FILE
		                output to file (incompatible with --output-fd, default is stdout)
	  --output-fd NUM       output to existing file descriptor (incompatible with -O)
	  -F {rtl_power,rtl_power_fftw,soapy_power_bin}, --format {rtl_power,rtl_power_fftw,soapy_power_bin}
		                output format (default: rtl_power)
	  -q, --quiet           limit verbosity
	  --debug               detailed debugging messages
	  --detect              detect connected SoapySDR devices and exit
	  --info                show info about selected SoapySDR device and exit
	  --version             show program's version number and exit

	FFT bins:
	  -b BINS, --bins BINS  number of FFT bins (incompatible with -B, default: 512)
	  -B Hz, --bin-size Hz  bin size in Hz (incompatible with -b)

	Averaging:
	  -n REPEATS, --repeats REPEATS
		                number of spectra to average (incompatible with -t and -T, default: 1600)
	  -t SECONDS, --time SECONDS
		                integration time (incompatible with -T and -n)
	  -T SECONDS, --total-time SECONDS
		                total integration time of all hops (incompatible with -t and -n)

	Measurements:
	  -c, --continue        repeat the measurement endlessly (incompatible with -u and -e)
	  -u RUNS, --runs RUNS  number of measurements (incompatible with -c and -e, default: 1)
	  -e SECONDS, --elapsed SECONDS
		                scan session duration (time limit in seconds, incompatible with -c and -u)

	Device settings:
	  -d DEVICE, --device DEVICE
		                SoapySDR device to use
	  -C CHANNEL, --channel CHANNEL
		                SoapySDR RX channel (default: 0)
	  -A ANTENNA, --antenna ANTENNA
		                SoapySDR selected antenna
	  -r Hz, --rate Hz      sample rate (default: 2000000.0)
	  -w Hz, --bandwidth Hz
		                filter bandwidth (default: 0)
	  -p PPM, --ppm PPM     frequency correction in ppm
	  -g dB, --gain dB      total gain (incompatible with -G and -a, default: 37.2)
	  -G STRING, --specific-gains STRING
		                specific gains of individual amplification elements (incompatible with -g and -a, example: LNA=28,VGA=12,AMP=0
	  -a, --agc             enable Automatic Gain Control (incompatible with -g and -G)
	  --lnb-lo Hz           LNB LO frequency, negative for upconverters (default: 0)
	  --device-settings STRING
		                SoapySDR device settings (example: biastee=true)
	  --force-rate          ignore list of sample rates provided by device and allow any value
	  --force-bandwidth     ignore list of filter bandwidths provided by device and allow any value
	  --tune-delay SECONDS  time to delay measurement after changing frequency (to avoid artifacts)
	  --reset-stream        reset streaming after changing frequency (to avoid artifacts)

	Crop:
	  -o PERCENT, --overlap PERCENT
		                percent of overlap when frequency hopping (incompatible with -k)
	  -k PERCENT, --crop PERCENT
		                percent of crop when frequency hopping (incompatible with -o)

	Performance options:
	  -s BUFFER_SIZE, --buffer-size BUFFER_SIZE
		                base buffer size (number of samples, 0 = auto, default: 0)
	  -S MAX_BUFFER_SIZE, --max-buffer-size MAX_BUFFER_SIZE
		                maximum buffer size (number of samples, -1 = unlimited, 0 = auto, default: 0)
	  --even                use only even numbers of FFT bins
	  --pow2                use only powers of 2 as number of FFT bins
	  --max-threads NUM     maximum number of PSD threads (0 = auto, default: 0)
	  --max-queue-size NUM  maximum size of PSD work queue (-1 = unlimited, 0 = auto, default: 0)
	  --no-pyfftw           don't use pyfftw library even if it is available (use scipy.fftpack or numpy.fft)

	Other options:
	  -l, --linear          linear power values instead of logarithmic
	  -R, --remove-dc       interpolate central point to cancel DC bias (useful only with boxcar window)
	  -D {none,constant}, --detrend {none,constant}
		                remove mean value from data to cancel DC bias (default: none)
	  --fft-window {boxcar,hann,hamming,blackman,bartlett,kaiser,tukey}
		                Welch's method window function (default: hann)
	  --fft-window-param FLOAT
		                shape parameter of window function (required for kaiser and tukey windows)
	  --fft-overlap PERCENT
		                Welch's method overlap between segments (default: 50)
	  --threshold FLOAT     Power threshold for signal measurements in decibel milliwatts (dBm). Default -85dBm
	  --server SERVER       IPv4 address for server. Default 127.0.0.1
	  --port PORT           UDP port for (JSON) signal measurements. Default 2048
	  --plot PLOT           Plot data to PNG files in /tmp. ON 1, OFF 0. Default 0


Example
-------
Using an Ettus B200, scan the 2.4GHz band with 45dB gain and produce a 128 point FFT with a 10ms dwell, -100dBm threshold, 50% tuning overlap and plot signals to /tmp.

    soapy_power -r 16M -f 2400M:2480M -g 45 -d driver=uhd -b 128 -t 0.01 --threshold -100 -c -o 50 --plot 1

Output:

	{
	 "reportTime": "2021-01-07 10:01:54.203655",
	 "frequencyMHz": 2421.875,
	 "bandwidthKHz": 1250,
	 "psd": [-116,-107,-102,-104,-107,-98,-97,-98,-107,-94,-88,-90,-94,-104,-101,-100,-111,-101,-101,-96,-90,-97,-102,-107,-113,-107,-110,-114,-112,-109,-109,-113,-111,-110,-112,-118,-114,-115,-107,-97,-94,-101,-103,-100,-100,-105,-109,-104,-113,-96,-92,-97,-104,-103,-118,-106,-108,-114,-104,-96,-93,-101,-105,-102,-102,-105,-112,-117,-119,-118,-117,-116,-120,-117,-116,-121,-115,-111,-111,-118,-122,-114,-113,-114,-115,-115,-123,-122,-116,-115,-115,-114,-115,-117,-120,-116,-114,-115,-116,-116,-117,-117,-117,-125,-118,-119,-123,-122,-119,-117,-118,-117,-118,-122,-120,-125,-120,-118,-115,-112,-115,-124,-118,-115,-115,-120,-121,-124],
	 "spanMHz": [2420.000,2436.000], 
	 "durationMs": 0.013,
	 "rssidBm": -88.7
	}
	{
	 "reportTime": "2021-01-07 10:01:54.997003",
	 "frequencyMHz": 2434.000,
	 "bandwidthKHz": 250,
	 "psd": [-120,-119,-119,-118,-118,-118,-118,-118,-117,-118,-118,-117,-115,-113,-110,-109,-107,-108,-110,-112,-115,-117,-117,-116,-116,-116,-116,-117,-117,-117,-116,-115,-116,-117,-117,-116,-116,-116,-117,-117,-117,-118,-117,-117,-116,-116,-118,-117,-117,-117,-117,-117,-117,-117,-116,-117,-117,-117,-119,-117,-116,-116,-117,-117,-116,-116,-116,-117,-116,-116,-116,-117,-117,-116,-115,-116,-117,-116,-116,-117,-116,-116,-116,-116,-115,-115,-116,-115,-116,-115,-116,-116,-116,-116,-115,-116,-116,-115,-114,-115,-114,-113,-106,-97,-91,-90,-90,-78,-70,-66,-63,-61,-59,-61,-62,-65,-69,-75,-86,-91,-91,-96,-105,-111,-113,-116,-117,-118],
	 "spanMHz": [2420.000,2436.000], 
	 "durationMs": 0.279,
	 "rssidBm": -59.6
	}


