================
Circuit Analysis
================


Introduction
============

Lcapy can only analyse linear time invariant (LTI) circuits, this
includes both passive and active circuits.  Time invariance means that
the circuit parameters cannot change with time; i.e., capacitors
cannot change value with time.  It also means that the circuit
configuration cannot change with time, i.e., contain switches
(although switching problems can be analysed, see
:ref:`switching-analysis`).

Linearity means that superposition applies---if you double the voltage
of a source, the current (anywhere in the circuit) due to that source
will also double.  This restriction rules out components such as
diodes and transistors that have a non-linear relationship between
current and voltage (except in circumstances where the relationship
can be approximated as linear around some constant value---small
signal analysis).  Linearity also rules out capacitors where the
capacitance varies with voltage and inductors with hysteresis.

Superposition_ allows a circuit to be analysed by considering the
effect of each independent current and voltage source in isolation and
summing the results.


Networks and netlists
=====================

Lcapy circuits can be created using a netlist specification (see
:ref:`netlists`) or by combinations of components (see
:ref:`networks`).  For example, here are two ways to create the same
circuit:

   >>> cct1 = (Vstep(10) + R(1)) | C(2)

   >>> cct2 = Circuit()
   >>> cct2.add('V 1 0 step 10')
   >>> cct2.add('R 1 2 1')
   >>> cct2.add('C 2 0 2')

The two approaches have many attributes and methods in common.  For example,

   >>> cct1.is_causal
   True
   >>> cct2.is_causal
   True
   >>> cct1.is_dc
   False
   >>> cct2.is_dc
   False

However, there are subtle differences.  For example,

   >>> cct1.Voc
      5   
   ──────
    2   s
   s  + ─
        2

   >>> cct2.Voc(2, 0)
      5   
   ──────
    2   s
   s  + ─
        2

Notice, the second example requires specific nodes to determine the
open-circuit voltage across.


Linear circuit analysis
=======================

There is no universal analytical technique to determine the voltages
and currents in an LTI circuit.  Instead there are a number of methods
that all try to side step having to solve simultaneous
integro-differential equations.  These methods include DC analysis, AC
analysis, and Laplace analysis.  Lcapy uses all three.


DC analysis
-----------

The simplest special case is for a DC independent source.  DC is an
idealised concept---it impossible to generate---but is a good 
approximation for very slowly changing sources.  With a DC independent
source the dependent sources are also DC and thus no voltages or
currents change.  Thus capacitors can be replaced with open-circuits
and inductors can be replaced with short-circuits.  

Lcapy performs a DC analysis if all the independent sources are DC and
no reactive component (L or C) has an initial condition explicitly
specified.  The latter constraint may be relaxed one day if the
initial condition can be proven not to create a transient.  A DC
problem when the `is_dc` attribute is True.  For example:

   >>> (Vdc(10) + C(1)).is_dc
   True
   >>> (Vdc(10) + C(1, 0)).is_dc
   False

The second example returns False since the capacitor has an explicit
initial condition.  In this case it is solved as an initial value
problem using Laplce analysis:

   >>> (Vdc(10) + C(1, 0)).is_ivp
   True


AC analysis
-----------

AC, like DC, is an idealised concept.  It allows circuits to be
analysed using phasors and impedances.  The use of impedances avoids
solving integro-differential equations in the time domain.

Lcapy performs AC analysis if all the independent sources are AC (and
of the same frequency) and no reactive component (L or C) has an
initial condition explicitly specified.  An AC
problem when the `is_ac` attribute is True.  For example:

   >>> (Vac(10) + C(1)).is_ac
   True
   >>> (Vac(10) + C(1, 0)).is_ac
   False



Laplace analysis
----------------

The response due to a transient excitation from an independent source
can be analysed using Laplace analysis.  This is what Lcapy was
originally designed for.  Since the unilateral transform is not unique
(it ignores the circuit behaviour for :math:`t < 0`), the response can
only be determined for :math:`t \ge 0`.

If the independent sources are known to be causal (a causal signal is
zero for :math:`t < 0` analogous to a causal impulse response) and the
initial conditions (i.e., the voltages across capacitors and currents
through inductors) are zero, then the response is 0 for :math:`t < 0`.
Thus in this case, the response can be specified for all :math:`t`.

The response due to a general non-causal excitation is hard to
determine using Laplace analysis.  One strategy is to use circuit
analysis techniques to determine the response for :math:`t < 0`,
compute the pre-initial conditions, and then use Laplace analysis to
determine the response for :math:`t \ge 0`.  Note, the pre-initial
conditions at :math:`t = 0_{-}` are required.  These differ from the
initial conditions at :math:`t = 0_{-}` whenever a Dirac delta (or its
derivative) excitation is considered.  Determining the initial
conditions is not straightforward for arbitrary excitations and at the
moment Lcapy expects you to do this!

The use of pre-initial conditions also allows switching circuits to be
considered (see :ref:`switching-analysis`).  In this case the
independent sources are ignored for :math:`t < 0` and the result is
only known for :math:`t \ge 0`.

Note if any of the pre-initial conditions are non-zero and the
independent sources are causal then either we have an initial value
problem or a mistake has been made.  Lcapy assumes that if all the
inductors and capacitors have explicit initial conditions, then the
circuit is to be analysed as an initial value problem with the
independent sources ignored for :math:`t \ge 0`.  In this case a DC
source is not DC since it is considered to switch on at :math:`t = 0`.

Lcapy performs Laplace analysis when neither the `is_ac` nor the
`is_dc` attribute is True.


.. _switching-analysis:

Switching analysis
------------------

Whenever a circuit has a switch it is time variant.  The opening or
closing of switch changes the circuit and can produce transients.
While a switch violates the LTI requirements for linear circuit
analysis, the circuit prior to the switch changing can be analysed and
used to determine the initial conditions for the circuit after the
switched changed.  Lcapy requires that you do this!  The independent
sources are ignored for :math:`t < 0` and the result is only known for
:math:`t \ge 0`.


Superposition
-------------

In principle, Lcapy could perform a combination of DC, AC, and Laplace
analysis to determine the overall result using superposition.

Lcapy will happily kill a specified independent source using the
`kill_except` method and thus s-domain superposition can be manually
performed.
