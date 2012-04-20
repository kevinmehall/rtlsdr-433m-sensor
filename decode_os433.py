from gnuradio import gr
import matplotlib.pyplot as plt
import gr_queue
from gnuradio import blks2
from gnuradio import audio
from gnuradio.gr import firdes
import osmosdr
		
		
thresh = -22
rate = 22050
audio_rate = 44100
device_rate = audio_rate * 25
freq_offs = -100e3
freq = 433.8e6

level = -0.35

osmosdr_source = osmosdr.source_c("")
osmosdr_source.set_center_freq(freq)
osmosdr_source.set_samp_rate(device_rate)

taps = firdes.low_pass(1, device_rate, 40000, 5000, firdes.WIN_HAMMING, 6.76)
freq_filter = gr.freq_xlating_fir_filter_ccc(25, taps, freq_offs, device_rate)

am_demod = blks2.am_demod_cf(
	channel_rate=audio_rate,
	audio_decim=1,
	audio_pass=5000,
	audio_stop=5500,
)
resampler = blks2.rational_resampler_fff(
	interpolation=1,
	decimation=2,
)
audio_sink = audio.sink(audio_rate, "", True)
sink = gr_queue.queue_sink_f()


tb = gr.top_block()
tb.connect(osmosdr_source, freq_filter, am_demod)
tb.connect(am_demod, audio_sink)
tb.connect(am_demod, resampler, sink)

tb.start()

def handle_packet(bytes):
	checksum = bytes[0] + bytes[1] + bytes[2]
	valid = (checksum&0xff == bytes[3])
	channel = 1 + (bytes[0] >> 6)
	t2 = bytes[1] >> 4
	t3 = bytes[1] & 0x0f
	t1 = bytes[2] & 0x0f
	sign = bool(bytes[2] & (1<<5))
	batt = bool(bytes[2] & (1<<7))
	hbit = bool(bytes[2] & (1<<6))
	temp = t1*10 + t2 + t3 / 10.0
	if sign: temp *= -1
	
	temp = temp * 9.0/5.0 + 32
	print 'received:', valid, channel, temp, batt, hbit

def transition(data, level=-0.2):
	last = False
	last_i = 0
	for i, val in enumerate(data):
		state = (val > level)
		if state != last:
			yield (state, i-last_i, i)
			last_i = i
			last = state


state = 'wait'
count = 0
bit = False
pkt = []

htimes = []
ltimes = []

for level, time, abstime in transition(sink, level):
	time = time / float(rate) * 1e6
	#print time, level
	
	if state == 'wait' and level:
		state = 'preamble'
		count = 0
		pkt = []
		#print "Start preamble"
	elif state == 'preamble':
		if not level:
			if (900 < time < 2250):
				#print "preamble falling", count
				count += 1
			else:
				state = 'wait'
		else:
			if (700 < time < 1400):
				#print "preamble rising", count
				pass
			elif count>8 and (2700 < time < 5000):
				state = 'sync'
				#print "sync rise"
			else:
				state = 'wait'
	elif state == 'sync':
		if not level:
			if (4500 < time < 6800):
				#print "sync fall"
				pass
			else:
				state = "wait"
		else:
			if (5600 < time < 6450):
				#print "After short sync", time, pkt
				state = "data"
				bit = 1
				pkt.append(1)
				
			elif (6450 < time < 7000):
				state = 'data'
				bit = 0
				pkt.append(0)
				#print "After long sync", time
			
			else:
				print "invalid after sync", time
				state = 'wait'
	elif state == 'data':
		if level:
			htimes.append(time)
			if (700 < time < 1700):
				if bit == 0:
					#print "repeat bit 0", time
					pkt.append(0)
			elif (1700 < time < 3500):
				pkt.append(0)
				#print "change bit 0", time
				bit = 0
			else:
				state = 'wait'
		else:
			ltimes.append(time)
			if (1500 < time < 2500):
				if bit == 1:
					#print "repeat bit 1", time
					pkt.append(1)
			elif (2500 < time < 4000):
				#print "change bit 1", time
				pkt.append(1)
				bit = 1
			else:
				print "invalid l data time", time
				state = 'wait'
		if len(pkt) >= 32:
			bytestr = [''.join(str(b) for b in pkt[i*8:i*8+8][::-1]) for i in range(0, 4)]
			bytes = [int(i, 2) for i in bytestr]
			print "pkt done", ' '.join(bytestr), bytes
			handle_packet(bytes)
			state = 'wait'
			
#print htimes
#print ''
#print ltimes

#plt.hist(ltimes, bins=50)

#plt.show()

