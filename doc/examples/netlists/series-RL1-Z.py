from lcapy import *
from numpy import logspace
from matplotlib.pyplot import figure, savefig, show

N = R(10) + L(1e-2)

f = logspace(0, 5, 400)
Z = N.Z.frequency_response(f)

fig = figure()
ax = fig.add_subplot(111)
ax.loglog(f, abs(Z), linewidth=2)
ax.set_xlabel('Frequency (Hz)')
ax.set_ylabel('Impedance (ohms)')
ax.grid(True)
show()

savefig('series-RL1-Z.png')
