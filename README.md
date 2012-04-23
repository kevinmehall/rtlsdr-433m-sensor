Decoding Oregon Scientifics wireless sensor data with RTL-SDR and GNU Radio
===========================================================================

Kevin Mehall <km@kevinmehall.net>
http://kevinmehall.net

This script decodes the packets that Oregon Scientifics remote
thermometers (like the one pictured below) send to the display unit. It also
serves as example code for accessing [rtl-sdr][] / GNU Radio samples live from
Python.

![Picture of sensor](http://kevinmehall.net/s/2012/oregon-scientific-sensor.jpeg)

Each sensor transmits every 30 seconds on 433.9MHz. The packet is repeated
twice. Modulation is [On-off keying][ook], and the 32 data bits are
[manchester encoded][manchester]. Alexander Yerezeyev implemeted a
[decoder for AVR][avr-code] microcontrollers, and wrote up a
[description of the protocol][alyer].

My sensors use the V1 protocol, but if you have newer sensors, take a look at
[JeeLabs' description][jeelabs-v2] of the V2 protocol. It would probably be
simple to adapt my code.

[rtl-sdr]: http://sdr.osmocom.org/trac/wiki/rtl-sdr 
[ook]: http://en.wikipedia.org/wiki/On-off_keying
[manchester]: http://en.wikipedia.org/wiki/Manchester_encoding
[alyer]: http://alyer.frihost.net/thn128decoding.htm
[avr-code]: http://code.google.com/p/thn128receiver/source/browse/osv1_dec.c
[jeelabs-v2]: http://jeelabs.net/projects/11/wiki/Decoding_the_Oregon_Scientific_V2_protocol

The GNU Radio [osmosdr block] captures from the [device][p160].
It's tuned slightly to the side to avoid the DC noise at the local oscillator
frequency. A `freq_xlating_fir_filter_ccc` block selects and downsamples the
correct region of the captured sensors. Then it AM demodulates that band, and
uses a message sink and queue to bring the samples into Python. (see gr_queue.py).
A Python state machine detects the preamble, manchester-decodes the bits, and
then parses the packet.

[osmosdr block]: http://cgit.osmocom.org/cgit/gr-osmosdr/
[p160]: http://blog.kevinmehall.com/post/21103573304/my-10-96-software-defined-radio-arrived

