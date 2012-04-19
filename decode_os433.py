from gnuradio import gr
import matplotlib.pyplot as plt
import gr_queue
				
src = gr.file_source(gr.sizeof_float, "433.bin")
sink = gr_queue.queue_sink_f()
tb = gr.top_block()
tb.connect(src, sink)

tb.start()

def queue_iterator(queue_sink):
	while True:
		yield sink.pop()

level = -0.35
rate = 44100.0

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

for level, time, abstime in transition(queue_iterator(sink), level):
	time = time / rate * 1e6
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

