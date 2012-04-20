"""
Decoder for Oregon Scientifics wireless temperature sensors (version 1 protocol)
using RTL-SDR and GNU Radio

(C) 2012 Kevin Mehall <km@kevinmehall.net>
Licensed under the terms of the GNU GPLv3+
"""

from gnuradio import gr
import gr_queue
from gnuradio import blks2
from gnuradio import audio
from gnuradio.gr import firdes
import osmosdr

# Sensors transmit on 433.9MHz
# The RTL-SDR has more noise near the center frequency, so we tune to the side
# and then shift the frequency in the low-pass filter.
freq = 433.8e6
freq_offs = 100e3

# Threshold for OOK HIGH level
level = -0.35

class rtlsdr_am_stream(gr.top_block):
	""" A GNU Radio top block that demodulates AM from RTLSDR and acts as a 
	python iterator for AM audio samples.
	
	Optionally plays the audio out the speaker.
	"""

	def __init__(self, center_freq, offset_freq, decimate_am=1, play_audio=False):
		"""Configure the RTL-SDR and GNU Radio"""
		super(rtlsdr_am_stream, self).__init__()
		
		audio_rate = 44100
		device_rate = audio_rate * 25
		output_rate = audio_rate / float(decimate_am)
		self.rate = output_rate

		self.osmosdr_source = osmosdr.source_c("")
		self.osmosdr_source.set_center_freq(freq)
		self.osmosdr_source.set_samp_rate(device_rate)

		taps = firdes.low_pass(1, device_rate, 40000, 5000, firdes.WIN_HAMMING, 6.76)
		self.freq_filter = gr.freq_xlating_fir_filter_ccc(25, taps, -freq_offs, device_rate)

		self.am_demod = blks2.am_demod_cf(
			channel_rate=audio_rate,
			audio_decim=1,
			audio_pass=5000,
			audio_stop=5500,
		)
		self.resampler = blks2.rational_resampler_fff(
			interpolation=1,
			decimation=decimate_am,
		)
		self.sink = gr_queue.queue_sink_f()
		
		self.connect(self.osmosdr_source, self.freq_filter, self.am_demod)
		self.connect(self.am_demod, self.resampler, self.sink)
		
		if play_audio:
			self.audio_sink = audio.sink(audio_rate, "", True)
			self.connect(self.am_demod, self.audio_sink)
			
	def __iter__(self):
		return self.sink.__iter__()

def transition(data, level=-0.35):
	"""Threshold a stream and yield transitions and their associated timing.
	Used to detect the On-Off-Keying (OOK)"""
	
	last = False
	last_i = 0
	for i, val in enumerate(data):
		state = (val > level)
		if state != last:
			yield (state, i-last_i, i)
			last_i = i
			last = state

def decode_osv1(stream, level=-0.35):
	"""Generator that takes an audio stream iterator and yields packets.
	State machine detects the preamble, and then manchester-decodes the packet """
	
	state = 'wait'
	count = 0
	bit = False
	pkt = []

	for direction, time, abstime in transition(stream, level):
		# convert the time in samples to microseconds
		time = time / float(stream.rate) * 1e6 

		if state == 'wait' and direction is True:
			# Start of the preamble
			state = 'preamble'
			count = 0
			pkt = []
			
		elif state == 'preamble':
			if direction is False:
				if (900 < time < 2250):
					# Valid falling edge in preamble
					count += 1
				else:
					state = 'wait'
			else:
				if (700 < time < 1400):
					# Valid rising edge in preamble
					pass
				elif count>8 and (2700 < time < 5000):
					# Preamble is over, this was the rising edge of the sync pulse
					state = 'sync'
				else:
					state = 'wait'
		elif state == 'sync':
			if direction is False:
				if (4500 < time < 6800):
					# Falling edge of sync pulse
					pass
				else:
					state = 'wait'
			else:
				# The time after the sync pulse also encodes the first bit of data
				if (5000 < time < 6000):
					# Short sync time starts a 1
					# I haven't actually seen this. Time is a guess
					state = 'data'
					bit = 1
					pkt.append(1)
				
				elif (6000 < time < 7000):
					# Long sync time starts a 0 (because a manchester-encoded 0 begins low)
					state = 'data'
					bit = 0
					pkt.append(0)
			
				else:
					print "invalid after sync", time
					state = 'wait'
		elif state == 'data':
			# Manchester decoding
			if direction is True:
				# Rising edge (end of LOW level)
				if (700 < time < 1700):
					if bit == 0:
						# A short LOW time means the 0 bit repeats
						pkt.append(0)
				elif (1700 < time < 3500):
					# A long LOW time means the start of a 0 bit
					pkt.append(0)
					bit = 0
				else:
					state = 'wait'
			else:
				# Falling edge (end of HIGH level)
				if (1500 < time < 2500):
					if bit == 1:
						# a short HIGH time is a repeated 1 bit
						pkt.append(1)
				elif (2500 < time < 4000):
					# A long HIGH time means the start of a 1 bit
					pkt.append(1)
					bit = 1
				else:
					print "invalid l data time", time
					state = 'wait'
			if len(pkt) >= 32:
				# Packet complete. Reverse the bits in each byte, convert them to ints, and decode the data
				bytestr = [''.join(str(b) for b in pkt[i*8:i*8+8][::-1]) for i in range(0, 4)]
				bytes = [int(i, 2) for i in bytestr]
				yield Packet(bytes)
				state = 'wait'

class Packet(object):		
	def __init__(self, bytes):
		""" Parse a binary packet into usable fields. """
		self.bytes = bytes
		
		checksum = bytes[0] + bytes[1] + bytes[2]
		self.valid = (checksum&0xff == bytes[3]) or (checksum&0xff + checksum>>8 == bytes[3])
		
		self.channel = 1 + (bytes[0] >> 6)
		
		t2 = bytes[1] >> 4
		t3 = bytes[1] & 0x0f
		t1 = bytes[2] & 0x0f
		sign = bool(bytes[2] & (1<<5))
		temp = t1*10 + t2 + t3 / 10.0
		if sign: temp *= -1
		self.temp_c = temp
		self.temp_f = temp * 9.0/5.0 + 32
		
		self.batt = bool(bytes[2] & (1<<7))
		self.hbit = bool(bytes[2] & (1<<6))
		
	def hex(self):
		return ' '.join('%02X'%x for x in self.bytes)
		
if __name__ == '__main__':
	stream = rtlsdr_am_stream(freq, freq_offs, decimate_am=1, play_audio=True)
	stream.start()
	unit = 'F'
	for packet in decode_osv1(stream):
		flags = []
		
		if not packet.valid:
			flags.append('[Invalid Checksum]')
		
		if packet.batt:
			flags.append('[Battery Low]')
			
		if packet.hbit:
			flags.append('[Sensor Failure]')
			
		if unit is 'F':
			temp = packet.temp_f
		else:
			temp = packet.temp_c
		
		print "{hex} = Channel {channel}: {temp} {unit}  {flags}".format(
			channel=packet.channel,
			temp=temp,
			unit = unit,
			flags = ' '.join(flags),
			hex = packet.hex()
		)

