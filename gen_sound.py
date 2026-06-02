import wave
import random
import struct

sample_rate = 44100
duration = 0.15 # seconds
num_samples = int(sample_rate * duration)

with wave.open("hit.wav", "w") as f:
    f.setnchannels(1)
    f.setsampwidth(2) # 16-bit
    f.setframerate(sample_rate)
    
    # Generate 8-bit style hit (white noise with volume decay)
    for i in range(num_samples):
        volume = 1.0 - (i / num_samples) # Linear fade out
        sample = int(random.uniform(-32767, 32767) * volume * 0.4)
        f.writeframes(struct.pack('<h', sample))
