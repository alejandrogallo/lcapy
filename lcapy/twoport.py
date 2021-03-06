"""
This module supports simple linear two-port networks.

Copyright 2014, 2015, 2016 Michael Hayes, UCECE
"""

from __future__ import division
from warnings import warn
import sympy as sym
from lcapy.core import s, Vs, Is, Zs, Ys, Hs, cExpr, sExpr
from lcapy.core import WyeDelta, DeltaWye, Vector, Matrix
from lcapy.core import VsVector, IsVector, YsVector, ZsVector
from lcapy.oneport import OnePort, I, V, Y, Z, Thevenin, Norton
from lcapy.network import Network


# TODO:
# 1. Defer the choice of the two-port model.  For example, a T section
# would store the three sub-networks rather than generating a B matrix.
# The appropriate model would be generated when desired.  This would
# avoid the inversion of singular matrices. The downside is that each
# object would require methods to generate each type of two-port model.
#
# Some multiport networks, such as a shunt R, have a singular Z matrix.
# Thus switching to the Y matrix and back to the Z matrix produces a
# bogus result.  The same thing occurs for a series R; this has a
# singular Y matrix.
#
# 2. Fix handling of buffered two ports (amplifier / delay).


# Consider chaining a resistor shunt to a two-port network described by the
# A matrix A1.  The shunt has an A matrix A2.  The result has an A matrix A3.
#
# A1 = [A11 A12]
#      [A21 A22]
#
# A2 = [1     0]
#      [1/R   1]
#
# A3 = A1 * A2 = [A11 + A12/R  A12]
#                [A21 + A22/R  A22]
#
# We should get the same result by adding the Y matrices.
#
# Y1 = [A22/A12  -A11 A22 / A12 + A21]
#      [-1/A12                A11/A12]
#
# Y3 = [A22/A12  -A11 A22 / A12 + A21]
#      [-1/A12          A11/A12 + 1/R]
#
# but
#
# Y2 = [inf   inf]
#      [inf   inf]
#
# We can get the correct answer using:
#
# A2 = lim x->0  [1    x]
#                [1/R  1]
#
# Now det(A2) = lim x->0 (1 - x/R)
#
# and Y2 = lim x->0 [1/x   (1/x - 1/R)]
#                   [-1/x          1/x]
#
# Note when x=0, then
#
# Y2 = lim x->0 [1/0   1/0]
#               [-1/0  1/0]
#
# and we lose the information on R.
#
# The same problem occurs with a series R and the Z matrix.
#
# A2 = lim x->0  [1    R]
#                [x    1]
#
# Now det(A2) = lim x->0 (1 - R x)
#
# and Z2 = lim x->0 [1/x  1/x - R]
#                   [1/x      1/x]
#
# Thus it is advantageous to represent two-ports by the A (or B)
# matrix.  However, things will go wrong when we transform to the Y or
# Z matrix for specific cases.

__all__ = ('Chain', 'Par2', 'Ser2', 'Hybrid2', 'InverseHybrid2', 'Series',
           'Shunt', 'IdealTransformer', 'IdealGyrator', 'VoltageFollower',
           'VoltageAmplifier', 'IdealVoltageAmplifier', 'IdealDelay',
           'IdealVoltageDifferentiator', 'IdealVoltageIntegrator',
           'CurrentFollower', 'IdealCurrentAmplifier',
           'IdealCurrentDifferentiator', 'IdealCurrentIntegrator',
           'OpampInverter', 'OpampIntegrator', 'OpampDifferentiator',
           'TSection', 'TwinTSection', 'BridgedTSection', 'PiSection',
           'LSection', 'Ladder', 'GeneralTxLine', 'LosslessTxLine', 'TxLine')


def _check_oneport_args(args):

    for arg1 in args:
        if not isinstance(arg1, OnePort):
            raise ValueError('%s not a OnePort' % arg1)


class TwoPortMatrix(Matrix):

    def __new__(cls, *args):

        args = [sym.simplify(arg) for arg in args]

        if len(args) == 4:
            return super(TwoPortMatrix, cls).__new__(
                cls, ((args[0], args[1]), (args[2], args[3])))

        return super(TwoPortMatrix, cls).__new__(cls, *args)

    # The following properties are fallbacks when other conversions have
    # not been defined.

    @property
    def A(self):
        return AMatrix(self.B.inv())

    @property
    def B(self):
        return BMatrix(self.A.inv())

    @property
    def G(self):
        return GMatrix(self.H.inv())

    @property
    def H(self):
        return HMatrix(self.G.inv())

    @property
    def Y(self):
        return YMatrix(self.Z.inv())

    @property
    def Z(self):
        return ZMatrix(self.Y.inv())

    @property
    def A11(self):
        """Open-circuit inverse voltage ratio"""
        return self.A[0, 0]

    @property
    def A12(self):
        """Negative short-circuit transfer impedance"""
        return self.A[0, 1]

    @property
    def A21(self):
        """Negative short-circuit inverse current ratio"""
        return self.A[1, 0]

    @property
    def A22(self):
        """Open circuit transfer admittance"""
        return self.A[1, 1]

    @property
    def B11(self):
        """Open-circuit voltage gain"""
        return self.B[0, 0]

    @property
    def B12(self):
        """Negative short-circuit transfer impedance"""
        return self.B[0, 1]

    @property
    def B21(self):
        """Negative short-circuit current gain"""
        return self.B[1, 0]

    @property
    def B22(self):
        """Open-circuit transfer admittance"""
        return self.B[1, 1]

    @property
    def G11(self):
        """Open-circuit input admittance"""
        return self.G[0, 0]

    @property
    def G12(self):
        """Short-circuit reverse current gain"""
        return self.G[0, 1]

    @property
    def G21(self):
        """Open-circuit forward voltage gain"""
        return self.G[1, 0]

    @property
    def G22(self):
        """Short-circuit output impedance"""
        return self.G[1, 1]

    @property
    def H11(self):
        """Short-circuit input impedance"""
        return self.H[0, 0]

    @property
    def H12(self):
        """Open-circuit reverse voltage gain"""
        return self.H[0, 1]

    @property
    def H21(self):
        """Short-circuit forward current gain"""
        return self.H[1, 0]

    @property
    def H22(self):
        """Open-circuit output admittance"""
        return self.H[1, 1]

    @property
    def Y11(self):
        """Short-circuit input admittance"""
        return self.Y[0, 0]

    @property
    def Y12(self):
        """Short-circuit reverse transfer admittance"""
        return self.Y[0, 1]

    @property
    def Y21(self):
        """Short-circuit transfer admittance"""
        return self.Y[1, 0]

    @property
    def Y22(self):
        """Short-circuit output admittance"""
        return self.Y[1, 1]

    @property
    def Z11(self):
        """Open-cicuit input impedance"""
        return self.Z[0, 0]

    @property
    def Z12(self):
        """Open-cicuit transfer impedance"""
        return self.Z[0, 1]

    @property
    def Z21(self):
        """Open-cicuit reverse transfer impedance"""
        return self.Z[1, 0]

    @property
    def Z22(self):
        """Open-cicuit output impedance"""
        return self.Z[1, 1]


class AMatrix(TwoPortMatrix):

    """
    ::
       +-  -+     +-       -+   +-  -+
       | V1 |  =  | A11  A12|   | V2 |
       | I1 |     | A21  A22|   |-I2 |
       +-  -+     +-       -+   +-  -+

              +-         -+
       units  | 1     ohm |
              | 1/ohm   1 |
              +-         -+

    A buffered two-port has A12 = A22 = 0.

    A = inv(B)
    """

    @property
    def A(self):
        # Perhaps we should make a copy?
        return self

    @property
    def B(self):

        # Inverse
        det = self.det()
        if det == 0:
            warn('Producing dodgy B matrix')
        return BMatrix(self.A22 / det, -self.A12 / det,
                       -self.A21 / det, self.A11 / det)

    @property
    def H(self):

        if self.A22 == 0:
            warn('Producing dodgy H matrix')
        return HMatrix(self.A12 / self.A22, self.det() / self.A22,
                       -1 / self.A22, self.A21 / self.A22)

    @property
    def Y(self):

        # This produces a bogus Y matrix when A12 is zero (say for a
        # shunt element).   Note, it doesn't use A21.
        if self.A12 == 0:
            warn('Producing dodgy Y matrix')
        return YMatrix(self.A22 / self.A12, -self.det() / self.A12,
                       -1 / self.A12, self.A11 / self.A12)

    @property
    def Z(self):

        # This produces a bogus Z matrix when A21 is zero (say for a
        # series element).   Note, it doesn't use A12.
        if self.A21 == 0:
            warn('Producing dodgy Z matrix')
        return ZMatrix(self.A11 / self.A21, self.det() / self.A21,
                       1 / self.A21, self.A22 / self.A21)

    @property
    def Z1oc(self):
        """open-circuit input impedance"""
        # Z11
        return Zs(self.A11 / self.A21)

    @classmethod
    def Zseries(cls, Zval):

        if not isinstance(Zval, Zs):
            raise ValueError('Zval not Zs')

        return cls(1, Zval, 0, 1)

    @classmethod
    def Yseries(cls, Yval):

        if not isinstance(Yval, Ys):
            raise ValueError('Yval not Ys')

        return cls(1, 1 / Yval, 0, 1)

    @classmethod
    def Yshunt(cls, Yval):

        if not isinstance(Yval, Ys):
            raise ValueError('Yval not Ys')

        return cls(1, 0, Yval, 1)

    @classmethod
    def Zshunt(cls, Zval):

        if not isinstance(Zval, Zs):
            raise ValueError('Zval not Zs')

        return cls(1, 0, 1 / Zval, 1)

    @classmethod
    def transformer(cls, alpha):

        alpha = cExpr(alpha)

        return cls(1 / alpha, 0, 0, alpha)

    @classmethod
    def gyrator(cls, R):

        R = cExpr(R)

        return cls(0, R, 1 / R, 0)

    @classmethod
    def Lsection(cls, Z1, Z2):

        return cls.Zseries(Z1).chain(cls.Zshunt(Z2))

    @classmethod
    def Tsection(cls, Z1, Z2, Z3):

        return cls.Lsection(Z1, Z2).chain(cls.Zseries(Z3))

    @classmethod
    def Pisection(cls, Z1, Z2, Z3):

        return cls.Zshunt(Z1).chain(cls.Lsection(Z2, Z3))

    def chain(self, OP):

        return self * OP

    def cascade(self, OP):

        return self.chain(OP)


class BMatrix(TwoPortMatrix):

    """
    ::
       +-  -+     +-       -+   +-  -+
       | V2 |  =  | B11  B12|   | V1 |
       |-I2 |     | B21  B22|   | I1 |
       +-  -+     +-       -+   +-  -+

              +-         -+
       units  | 1     ohm |
              | 1/ohm   1 |
              +-         -+

    B = inv(A)
    """

    @property
    def A(self):
        # Inverse
        det = self.det()
        return AMatrix(
            self.B22 / det, -self.B12 / det, -self.B21 / det, self.B11 / det)

    @property
    def B(self):
        # Perhaps we should make a copy?
        return self

    @property
    def G(self):

        return GMatrix(-self.B21 / self.B22, -1 / self.B22,
                       self.det() / self.B22, -self.B12 / self.B22)

    @property
    def H(self):

        return HMatrix(-self.B12 / self.B11, 1 / self.B11, -
                       self.det() / self.B11, -self.B21 / self.B11)

    @property
    def Y(self):

        return YMatrix(-self.B11 / self.B12, 1 / self.B12,
                       self.det() / self.B12, -self.B22 / self.B12)

    @property
    def Z(self):

        return ZMatrix(-self.B22 / self.B21, -1 / self.B21, -
                       self.det() / self.B21, -self.B11 / self.B21)

    @property
    def Z1oc(self):
        """open-circuit input impedance"""
        # Z11
        return Zs(-self.B22 / self.B21)

    @classmethod
    def Zseries(cls, Zval):

        if not isinstance(Zval, Zs):
            raise ValueError('Zval not Zs')

        return cls(1, -Zval, 0, 1)

    @classmethod
    def Yseries(cls, Yval):

        if not isinstance(Yval, Ys):
            raise ValueError('Yval not Ys')

        return cls(1, -1 / Yval, 0, 1)

    @classmethod
    def Yshunt(cls, Yval):

        if not isinstance(Yval, Ys):
            raise ValueError('Yval not Ys')

        return cls(1, 0, -Yval, 1)

    @classmethod
    def Zshunt(cls, Zval):

        if not isinstance(Zval, Zs):
            raise ValueError('Zval not Zs')

        return cls(1, 0, -1 / Zval, 1)

    @classmethod
    def voltage_amplifier(cls, Af, Ar=1e-9, Yin=1e-9, Zout=1e-9):
        """Voltage amplifier
        Af forward voltage gain
        Ar reverse voltage gain (ideally 0)
        Yin input admittance (ideally 0)
        Zout output impedance (ideally 0)
        """

        if Ar == 0 and Yin == 0 and Zout == 0:
            warn('Should use G matrix; tweaking B matrix to make invertible')
            Ar = 1e-9
            Yin = 1e-9
            Zout = 1e-9

        Af = sExpr(Af)
        Ar = sExpr(Ar)
        Yin = sExpr(Yin)
        Zout = sExpr(Zout)

        # This should be defined with a G matrix
        #
        # G = [0   0]
        #     [Af  0]
        #
        # With this model, the inverse voltage gain is 1 / Af
        #
        # G = lim x->0  [0   x]
        #               [Af  0]
        #
        # B = lim x->0  [Af    0/x]
        #               [0/x  -1/x]
        #
        # A = lim x->0  [1/Af 0/Af]
        #               [0/Af   -x]

        # Perhaps default Ar, Yin, and Zout to 1e-10 to get a reasonable
        # B matrix?

        return cls(1 / Ar, -1 / (Ar * Yin), -1 / (Ar * Zout), -
                   1 / (Ar * Yin * Zout * (Af * Ar - 1)))

    @classmethod
    def current_amplifier(cls, Af, Ar=1e-9, Zin=1e-9, Yout=1e-9):
        """Current amplifier
        Af forward current gain
        Ar reverse current gain (ideally 0)
        Yin input admittance (ideally 0)
        Yout output impedance (ideally 0)
        """

        if Ar == 0 and Zin == 0 and Yout == 0:
            warn('Should use G matrix; tweaking B matrix to make invertible')
            Ar = 1e-9
            Zin = 1e-9
            Yout = 1e-9

        Af = sExpr(Af)
        Ar = sExpr(Ar)
        Zin = sExpr(Zin)
        Yout = sExpr(Yout)

        # This should be defined with a H matrix
        #
        # H = [0   0]
        #     [Af  0]
        #
        # With this model, the inverse current gain is 1 / Af
        #
        # H = lim x->0  [0   x]
        #               [Af  0]
        #
        # B = lim x->0  [1/x    0]
        #               [0    -Af]
        #
        # A = lim x->0  [1/x  -0/x]
        #               [0/x   -Af]

        return cls(1 / Ar, -1 / (Ar * Yout), -1 / (Ar * Zin), -
                   1 / (Ar * Yout * Zin * (Af * Ar - 1)))

    @classmethod
    def voltage_differentiator(cls, Av=1):

        return cls.voltage_amplifier(sExpr(Av).differentiate())

    @classmethod
    def voltage_integrator(cls, Av):

        return cls.voltage_amplifier(sExpr(Av).integrate())

    @classmethod
    def current_differentiator(cls, Av):

        return cls.current_amplifier(sExpr(Av).differentiate())

    @classmethod
    def current_integrator(cls, Av):

        return cls.current_amplifier(sExpr(Av).integrate())

    @classmethod
    def transformer(cls, alpha):

        alpha = cExpr(alpha)

        return cls(alpha, 0, 0, 1 / alpha)

    @classmethod
    def gyrator(cls, R):

        R = cExpr(R)

        return cls(0, R, 1 / R, 0)

    @classmethod
    def Lsection(cls, Z1, Z2):

        Y = 1 / Z2
        return cls(1 + Y * Z1, -Z1, -Y, 1)
        # return cls.Zseries(Z1).chain(cls.Zshunt(Z2))

    @classmethod
    def Tsection(cls, Z1, Z2, Z3):

        Y = 1 / Z2
        return cls(1 + Y * Z1, -Z1 - Z3 * (1 + Y * Z1), -Y, 1 + Y * Z3)
        # return cls.Lsection(Z1, Z2).chain(cls.Zseries(Z3))

    @classmethod
    def Pisection(cls, Z1, Z2, Z3):

        return cls.Zshunt(Z1).chain(cls.Lsection(Z2, Z3))

    def chain(self, TP):

        # Note reverse order compared to AMatrix.
        return TP * self

    def cascade(self, TP):

        return self.chain(TP)


class GMatrix(TwoPortMatrix):

    """

    ::
       +-  -+     +-       -+   +-  -+
       | V2 |  =  | G11  G12|   | I2 |
       | I1 |     | G21  G22|   | V1 |
       +-  -+     +-       -+   +-  -+

              +-         -+
       units  | ohm     1 |
              | 1   1/ohm |
              +-         -+

    G = inv(H)
    """

    @property
    def A(self):
        # return self.H.A
        return AMatrix(1 / self.G21, self.G22 / self.G21,
                       self.G11 / self.G21, self.det() / self.G21)

    @property
    def B(self):
        # return self.H.B
        return BMatrix(-self.det() / self.G12, self.G22 /
                       self.G12, self.G11 / self.G12, -1 / self.G12)

    @property
    def G(self):
        # Perhaps we should make a copy?
        return self

    @property
    def H(self):
        return HMatrix(self.inv())

    @property
    def Y(self):
        return self.H.Y

    @property
    def Z(self):
        return self.H.Z


class HMatrix(TwoPortMatrix):

    """
    ::
       +-  -+     +-       -+   +-  -+
       | V1 |  =  | H11  H12|   | I1 |
       | I2 |     | H21  H22|   | V2 |
       +-  -+     +-       -+   +-  -+

              +-         -+
       units  | ohm     1 |
              | 1   1/ohm |
              +-         -+

    H = inv(G)
    """

    @property
    def A(self):
        return AMatrix(-self.det() / self.H21, -self.H11 /
                       self.H21, -self.H22 / self.H21, -1 / self.H21)

    @property
    def B(self):
        return BMatrix(1 / self.H12, -self.H11 / self.H12, -
                       self.H22 / self.H12, self.det() / self.H12)

    @property
    def H(self):
        # Perhaps we should make a copy?
        return self

    @property
    def Y(self):
        return YMatrix(1 / self.H11, -self.H12 / self.H11,
                       self.H21 / self.H11, self.det() / self.H11)

    @property
    def Z(self):
        return ZMatrix(self.det() / self.H22, self.H12 / self.H22,
                       -self.H21 / self.H22, 1 / self.H22)


class YMatrix(TwoPortMatrix):

    """
    ::
       +-  -+     +-       -+   +-  -+
       | I1 |  =  | Y11  Y12|   | V1 |
       | I2 |     | Y21  Y22|   | V2 |
       +-  -+     +-       -+   +-  -+

              +-           -+
       units  | 1/ohm 1/ohm |
              | 1/ohm 1/ohm |
              +-           -+

    Y = inv(Z)
    """

    @property
    def Ysc(self):
        return YsVector(self.Y11, self.Y22)

    @property
    def A(self):
        return AMatrix(-self.Y22 / self.Y21, -1 / self.Y21, -
                       self.det() / self.Y21, -self.Y11 / self.Y21)

    @property
    def B(self):
        return BMatrix(-self.Y11 / self.Y12, 1 / self.Y12,
                       self.det() / self.Y12, -self.Y22 / self.Y12)

    @property
    def H(self):
        return HMatrix(1 / self.Y11, -self.Y12 / self.Y11,
                       self.Y21 / self.Y11, self.det() / self.Y11)

    @property
    def Y(self):
        # Perhaps we should make a copy?
        return self

    @property
    def Z(self):
        # Inverse
        det = self.det()
        return ZMatrix(
            self.Y22 / det, -self.Y12 / det, -self.Y21 / det, self.Y11 / det)


class ZMatrix(TwoPortMatrix):

    """
    ::
       +-  -+     +-       -+   +-  -+
       | V1 |  =  | Z11  Z12|   | I1 |
       | V2 |     | Z21  Z22|   | I2 |
       +-  -+     +-       -+   +-  -+

              +-         -+
       units  | ohm   ohm |
              | ohm   ohm |
              +-         -+

    Z = inv(Y)
    """

    @property
    def Zoc(self):
        return ZsVector(self.Z11, self.Z22)

    @property
    def A(self):
        return AMatrix(self.Z11 / self.Z21, self.det() / self.Z21,
                       1 / self.Z21, self.Z22 / self.Z21)

    @property
    def B(self):
        return BMatrix(self.Z22 / self.Z12, -self.det() /
                       self.Z12, -1 / self.Z12, self.Z11 / self.Z12)

    @property
    def H(self):
        return HMatrix(self.det() / self.Z22, self.Z12 / self.Z22,
                       -self.Z21 / self.Z22, 1 / self.Z22)

    @property
    def Y(self):
        # Inverse
        det = self.det()
        return YMatrix(
            self.Z22 / det, -self.Z12 / det, -self.Z21 / det, self.Z11 / det)

    @property
    def Z(self):
        # Perhaps we should make a copy?
        return self

    @classmethod
    def Lsection(cls, Z1, Z2):
        return cls.Tsection(Z1 + Z2, Z2, Z2, Z2)

    @classmethod
    def Tsection(cls, Z1, Z2, Z3):
        # Note if Z3 is infinity then all elements of Z are infinite.
        # Thus we cannot model a single series R with a Z matrix.
        # A single shunt R works though.
        return cls(Z1 + Z2, Z2, Z2, Z2 + Z3)

    @classmethod
    def Pisection(cls, Z1, Z2, Z3):

        Za, Zb, Zc = DeltaWye(Z1, Z2, Z3)
        return cls.Tsection(Za, Zb, Zc)


class TwoPort(Network):

    """
    General class to two-port networks.  Two-port networks are
    constrained to have the same current at each port (but flowing in
    opposite directions).  This is called the port condition.
    """

    def _add_elements(self):
        raise ValueError('Cannot generate netlist for two-port objects')

    def netlist(self):
        raise ValueError('Cannot generate netlist for two-port objects')

    def _check_twoport_args(self):

        # This is an interim measure until Par2, Ser2, etc. generalised.
        if len(self.args) != 2:
            raise ValueError('Only two args supported for %s' %
                             self.__class__.__name__)
        for arg1 in self.args:
            if not isinstance(arg1, TwoPort):
                raise ValueError('%s not a TwoPort' % arg1)

    @property
    def A11(self):
        return self.A[0, 0]

    @property
    def A12(self):
        return self.A[0, 1]

    @property
    def A21(self):
        return self.A[1, 0]

    @property
    def A22(self):
        return self.A[1, 1]

    @property
    def B11(self):
        return self.B[0, 0]

    @property
    def B12(self):
        return self.B[0, 1]

    @property
    def B21(self):
        return self.B[1, 0]

    @property
    def B22(self):
        return self.B[1, 1]

    @property
    def G11(self):
        return self.G[0, 0]

    @property
    def G12(self):
        return self.G[0, 1]

    @property
    def G21(self):
        return self.G[1, 0]

    @property
    def G22(self):
        return self.G[1, 1]

    @property
    def H11(self):
        return self.H[0, 0]

    @property
    def H12(self):
        return self.H[0, 1]

    @property
    def H21(self):
        return self.H[1, 0]

    @property
    def H22(self):
        return self.H[1, 1]

    @property
    def Y11(self):
        return self.Y[0, 0]

    @property
    def Y12(self):
        return self.Y[0, 1]

    @property
    def Y21(self):
        return self.Y[1, 0]

    @property
    def Y22(self):
        return self.Y[1, 1]

    @property
    def Z11(self):
        return self.Z[0, 0]

    @property
    def Z12(self):
        return self.Z[0, 1]

    @property
    def Z21(self):
        return self.Z[1, 0]

    @property
    def Z22(self):
        return self.Z[1, 1]

    @property
    def isbuffered(self):
        """Return true if two-port is buffered, i.e., any load
        on the output has no affect on the input. """
        # return self.A12 == 0 and self.A22 == 0
        return self.B12 == 0 and self.B22 == 0

    @property
    def isbilateral(self):
        """Return true if two-port is bilateral. """
        return self.B.det() == 1

    @property
    def issymmetrical(self):
        """Return true if two-port is symmetrical. """
        return self.B11 == self.B22

    @property
    def isseries(self):
        """Return true if two-port is a series network. """
        # return (self.A11 == 1) and (self.A22 == 1) and (self.A21 == 0)
        return (self.B11 == 1) and (self.B22 == 1) and (self.B21 == 0)

    @property
    def isshunt(self):
        """Return true if two-port is a shunt network. """
        # return (self.A11 == 1) and (self.A22 == 1) and (self.A12 == 0)
        return (self.B11 == 1) and (self.B22 == 1) and (self.B12 == 0)

    @property
    def A(self):
        """Return chain matrix"""
        return self._M.A

    @property
    def B(self):
        """Return inverse chain matrix"""
        return self._M.B

    @property
    def G(self):
        """Return inverse hybrid matrix"""
        return self._M.G

    @property
    def H(self):
        """Return hybrid matrix"""
        return self._M.H

    @property
    def Y(self):
        """Return admittance matrix"""
        return self._M.Y

    @property
    def Z(self):
        """Return impedance matrix"""
        return self._M.Z

    @property
    def I1a(self):
        return Is(-self.V2b / self.B12)

    @property
    def V1a(self):
        # CHECKME
        return Vs(-self.I2b / self.B21)

    @property
    def I1g(self):
        return Is(-self.I2b / self.B22)

    @property
    def V2g(self):
        return Vs(self.V2b - self.B12 / self.B22 * self.I2b)

    @property
    def V1h(self):
        return Vs(-self.V2b / self.B11)

    @property
    def I2h(self):
        return Is(-self.V2b * self.B21 / self.B11) - self.I2b

    @property
    def I1y(self):
        return Is(-self.V2b / self.B12)

    @property
    def I2y(self):
        return Is(self.V2b * self.B22 / self.B12) - self.I2b

    @property
    def V1z(self):
        return Vs(-self.I2b / self.B21)

    @property
    def V2z(self):
        return self.V2b - Vs(self.I2b * self.B11 / self.B21)

    @property
    def Yoc(self):
        """Return admittance vector with ports open circuit"""
        return YsVector(Ys(1 / self.Z1oc), Ys(1 / self.Z2oc))

    @property
    def Y1oc(self):
        """Return input impedance with the output port open circuit"""
        return Zs(1 / self.Z1oc)

    @property
    def Y2oc(self):
        """Return output impedance with the input port open circuit"""
        return Ys(1 / self.Z2oc)

    @property
    def Ysc(self):
        """Return admittance vector with ports short circuit"""
        return self.Y.Ysc

    @property
    def Y1sc(self):
        """Return input admittance with output port short circuit"""
        return Ys(self.Ysc[0])

    @property
    def Y2sc(self):
        """Return output admittance with output port short circuit"""
        return Ys(self.Ysc[1])

    @property
    def Zoc(self):
        """Return impedance vector with ports open circuit"""
        return self.Z.Zoc

    @property
    def Z1oc(self):
        """Return input impedance with the output port open circuit"""
        return Zs(self.Zoc[0])

    @property
    def Z2oc(self):
        """Return output impedance with the input port open circuit"""
        return Zs(self.Zoc[1])

    @property
    def Zsc(self):
        """Return impedance vector with ports short circuit"""
        return ZsVector(Zs(1 / self.Y1sc), Zs(1 / self.Y2sc))

    @property
    def Z1sc(self):
        """Return input impedance with the output port short circuit"""
        return Zs(1 / self.Y1sc)

    @property
    def Z2sc(self):
        """Return output impedance with the input port short circuit"""
        return Zs(1 / self.Y2sc)

    def Vgain(self, inport=1, outport=2):
        """Return voltage gain for specified ports with internal
        sources zero"""

        # Av  = G21 = 1 / A11 = -det(B) / B22 = Z21 / Z11 =  Y21 / Y22
        # Av' = H12 = 1 / B11 =  |A| / A22 = Z12 / Z22 = -Y12 / Y11

        if inport == outport:
            return Hs(1)
        if inport == 1 and outport == 2:
            return Hs(1 / self.A11)
        if inport == 2 and outport == 1:
            return Hs(1 / self.B11)
        raise ValueError('bad port values')

    def Igain(self, inport=1, outport=2):
        """Return current gain for specified ports with internal
         sources zero"""

        # Ai  = H21 = -1 / A22 = -det(B) / B11 = -Z21 / Z22 = Y21 / Y11
        # Ai' = G12 =  1 / B22 =  |A| / A11 = -Z12 / Z11 = Y12 / Y22

        if inport == outport:
            return Hs(1)
        if inport == 1 and outport == 2:
            return Hs(-1 / self.A22)
        if inport == 2 and outport == 1:
            return Hs(-1 / self.B22)
        raise ValueError('bad port values')

    @property
    def Vgain12(self):
        """Return V2 / V1 for I2 = 0 (forward voltage gain) with
        internal sources zero

        Av = G21 = 1 / A11 = -det(B) / B22 = Z21 / Z11 =  Y21 / Y22
        """

        return self.Vgain(1, 2)

    @property
    def Vtransfer(self):
        """Return V2 / V1 for I2 = 0 (forward voltage gain) with
        internal sources zero  (see Vgain12)"""

        return self.Vgain12

    @property
    def Igain12(self):
        """Return I2 / I1 for V2 = 0 (forward current gain) with
        internal sources zero

        Ai = H21 = -1 / A22 = -det(B) / B11 = -Z21 / Z22 = Y21 / Y11
        """

        return self.Igain(1, 2)

    @property
    def Itransfer(self):
        """Return I2 / I1 for V2 = 0 (forward current gain) with
        internal sources zero  (sett Igain12)"""

        return self.Igain12

    def Vresponse(self, V, inport=1, outport=2):
        """Return voltage response for specified applied voltage and
        specified ports"""

        if issubclass(V.__class__, OnePort):
            V = V.Voc

        p1 = inport - 1
        p2 = outport - 1

        H = self.Z[p2, p1] / self.Z[p1, p1]
        return Vs(self.Voc[p2] + (V - self.Voc[p1]) * H)

    def Iresponse(self, I, inport=1, outport=2):
        """Return current response for specified applied current and
        specified ports"""

        if issubclass(I.__class__, OnePort):
            I = I.Isc

        p1 = inport - 1
        p2 = outport - 1

        Y = self.Y
        Isc = self.Isc

        return Is(Isc[p2] + Y[p2, p1] / Y[p1, p1] * (I - Isc[p1]))

    def Ytrans(self, inport=1, outport=2):
        """Return transadmittance for specified ports with internal
        sources zero"""

        return Ys(self.Y[outport - 1, inport - 1])

    @property
    def Ytrans12(self):
        """Return I2 / V1 for V2 = 0 (forward transadmittance) with
         internal sources zero

         Y21 = -1 / A12 = det(B) / B12
         """

        return Ys(self.Y21)

    @property
    def Ytransfer(self):
        """Return I2 / V1 for V2 = 0 (forward transadmittance) with
         internal sources zero.  This is an alias for Ytrans12.

         Y21 = -1 / A12 = det(B) / B12
         """

        return self.Ytrans12

    def Ztrans(self, inport=1, outport=2):
        """Return transimpedance for specified ports with internal
        sources zero"""

        return Zs(self.Z[outport - 1, inport - 1])

    def Ztrans12(self):
        """Return V2 / I1 for I2 = 0 (forward transimpedance) with
        internal sources zero

        Z21 = 1 / A21 = -det(B) / B21
        """

        return Zs(self.Z21)

    @property
    def Ztransfer(self):
        """Return V2 / I1 for I2 = 0 (forward transimpedance) with
        internal sources zero.  This is an alias for Ztrans12.

        Z21 = 1 / A21 = -det(B) / B21
        """

        return self.Ztrans12

    @property
    def V1oc(self):
        """Return V1 with all ports open-circuited (i.e., I1 = I2 = 0)"""
        return Vs(self.Voc[0])

    @property
    def V2oc(self):
        """Return V2 with all ports open-circuited (i.e., I1 = I2 = 0)"""
        return Vs(self.Voc[1])

    @property
    def I1sc(self):
        """Return I1 with all ports short-circuited, i.e, V1 = V2 = 0"""
        return Is(self.Isc[0])

    @property
    def I2sc(self):
        """Return I2 with all ports short-circuited, i.e, V1 = V2 = 0"""
        return Is(self.Isc[1])

    @property
    def Voc(self):
        """Return voltage vector with all ports open-circuited
        (i.e., In = 0)"""
        return VsVector(self.V1z, self.V2z)

    @property
    def Isc(self):
        """Return current vector with all ports short-circuited
        (i.e., V1 = V2 = 0)"""
        return IsVector(self.I1y, self.I2y)

    @property
    def Bmodel(self):

        return TwoPortBModel(self.B, self.V2b, self.I2b)

    @property
    def Hmodel(self):

        return TwoPortHModel(self.H, self.V1h, self.I2h)

    @property
    def Ymodel(self):

        if self.isshunt:
            warn('Converting a shunt two-port to a Y model is dodgy...')
        return TwoPortYModel(self.Y, self.I1y, self.I2y)

    @property
    def Zmodel(self):

        if self.isseries:
            warn('Converting a series two-port to a Z model is dodgy...')
        return TwoPortZModel(self.Z, self.V1z, self.V2z)

    def chain(self, TP):
        """Return the model with, TP, appended (cascade or
        chain connection)"""

        if not issubclass(TP.__class__, TwoPort):
            raise TypeError('Argument not', TwoPort)

        return Chain(self, TP)

    def append(self, TP):
        """Return the model with, TP, appended"""

        return self.chain(TP)

    def prepend(self, TP):
        """Return the model with, TP, prepended"""

        return TP.chain(self)

    def cascade(self, TP):
        """Return the model with, TP, appended"""

        return self.chain(TP)

    def series(self, TP, port=None):
        """Return the model with, TP, in series.

         In general, this is tricky to ensure that the port condition
         is valid.  The common ground connection of the first two-port
         shorts out the top of the T of the second two-port.
         """

        if issubclass(TP.__class__, OnePort):
            raise NotImplementedError('TODO')

        warn('Do you mean chain?  The result of a series combination'
             ' of two two-ports may be dodgy')

        return Ser2(self, TP)

    def terminate(self, OP, port=2):
        """Connect one-port in parallel to specified port and return
        a Thevenin (one-port) object"""

        if port == 1:
            return self.source(OP)
        if port == 2:
            return self.load(OP)
        raise ValueError('Invalid port ' + port)

    def parallel(self, TP, port=None):
        """Return the model with, TP, in parallel"""

        if issubclass(TP.__class__, OnePort):
            raise NotImplementedError('TODO')

        return Par2(self, TP)

    def hybrid(self, TP, port=None):
        """Return the model with, TP, in hybrid connection (series
        input, parallel output)"""

        if issubclass(TP.__class__, OnePort):
            raise NotImplementedError('TODO')

        return Hybrid2(self, TP)

    def inverse_hybrid(self, TP, port=None):
        """Return the model with, TP, in inverse hybrid connection
        (parallel input, series output)"""

        if issubclass(TP.__class__, OnePort):
            raise NotImplementedError('TODO')

        return InverseHybrid2(self, TP)

    # Other operations: swapping the input terminals negates the A matrix.
    # switching ports.

    def bridge(self, TP):
        """Bridge the ports with a one-port element"""

        if not issubclass(TP.__class__, OnePort):
            raise TypeError('Argument not ', OnePort)

        # FIXME
        return self.parallel(Series(TP))

    def load(self, TP):
        """Apply a one-port load and return a Thevenin (one-port) object"""

        if not issubclass(TP.__class__, OnePort):
            raise TypeError('Argument not ', OnePort)

        foo = self.chain(Shunt(TP))
        return Z(foo.Z1oc) + V(foo.V1oc)

    def source(self, TP):
        """Apply a one-port source and return a Thevenin (one-port) object"""

        if not issubclass(TP.__class__, OnePort):
            raise TypeError('Argument not ', OnePort)

        foo = Shunt(TP).chain(self)
        return Z(foo.Z2oc) +  V(foo.V2oc)

    def short_circuit(self, port=2):
        """Apply a short-circuit to specified port and return a
        one-port object"""

        p = port - 1
        Yval = self.Y[1 - p, 1 - p]
        Ival = self.Isc[1 - p]

        return Y(Yval) | I(Ival)

    def open_circuit(self, port=2):
        """Apply a open-circuit to specified port and return a
        one-port object"""

        p = port - 1
        Zval = self.Z[1 - p, 1 - p]
        Vval = self.Voc[1 - p]

        return Z(Zval) + V(Vval)

    def simplify(self):

        if self.B == sym.eye(2):
            # Have a pair of wires... perhaps could simplify
            # to an LSection comprised of a V and I but
            # may have a weird voltage expression.
            pass
        return self


class TwoPortBModel(TwoPort):

    """
    ::
            +-------------------+    +------+
     I1     |                   | I2'| -  + |          I2
    -->-----+                   +-<--+  V2b +----+-----<--
            |    two-port       |    |      |    |
    +       |    network        | +  +------+    |       +
    V1      |    without        | V2'        +---+---+  V2
    -       |    sources        | -          |   |   |   -
            |    represented    |               I2b  |
            |    by B matrix    |            |   v   |
            |                   |            +---+---+
            |                   |                |
    --------+                   +----------------+--------
            |                   |
            +-------------------+

    +-   +     +-        -+   +-  -+     +-   -+
    | V2 |  =  | B11  B12 |   | V1 |  +  | V2b |
    |-I2 |     | B21  B22 |   | I1 |     | I2b |
    +-  -+     +-        -+   +-  -+     +-   -+


    +-    +     +-        -+   +-  -+
    | V2' |  =  | B11  B12 |   | V1 |
    |-I2' |     | B21  B22 |   | I1 |
    +-   -+     +-        -+   +-  -+

    +-    +     +-  -+    +-   -+
    | V2' |  =  | V2 | -  | V2b |
    | I2' |     | I2'|    | I2b |
    +-  - +     +-  -+    +-   -+

    +-         +     +-        -+   +-  -+
    | V2 - V2b |  =  | B11  B12 |   | V1 |
    |-I2 - I2b |     | B21  B22 |   | I1 |
    +-        -+     +-        -+   +-  -+

    +-   +     +-        -+   +-    +
    | V1 |  =  | A11  A12 |   | V2' |
    | I1 |     | A21  A22 |   |-I2' |
    +-  -+     +-        -+   +-   -+

    +-   +     +-        -+   +-       -+
    | V1 |  =  | A11  A12 |   | V2 - V2b |
    | I1 |     | A21  A22 |   |-I2 + I2b |
    +-  -+     +-        -+   +-        -+

    """

    # A disadvantage of the Y and Z matrices is that they become
    # singular for some simple networks.  For example, the Z matrix is
    # singular for a shunt element and the Y matrix is singular for a
    # series element.  The A and B matrices do not seem to have this
    # problem, however, they cannot be extended to three or more ports.
    #

    def __init__(self, B, V2b=Vs(0), I2b=Is(0)):

        if issubclass(B.__class__, TwoPortBModel):
            B, V2b, I2b = B._M, B._V2b, B._I2b

        if not isinstance(B, BMatrix):
            raise ValueError('B not BMatrix')

        if not isinstance(V2b, Vs):
            raise ValueError('V2b not Vs')

        if not isinstance(I2b, Is):
            raise ValueError('I2b not Is')

        super(TwoPortBModel, self).__init__()
        self._M = B
        self._V2b = V2b
        self._I2b = I2b

    @property
    def B(self):
        """Return chain matrix"""
        return self._M

    @property
    def I2b(self):
        return self._I2b

    @property
    def V2b(self):
        return self._V2b

    @property
    def V1h(self):
        return Vs(-self.V2b / self.B11)

    @property
    def I2h(self):
        return Is(-self.V2b * self.B21 / self.B11) - self.I2b

    @property
    def I1y(self):
        return Is(-self.V2b / self.B12)

    @property
    def I2y(self):
        return Is(self.V2b * self.B22 / self.B12) - self.I2b

    @property
    def V1z(self):
        return Vs(-self.I2b / self.B21)

    @property
    def V2z(self):
        return self.V2b - Vs(self.I2b * self.B11 / self.B21)


class TwoPortGModel(TwoPort):

    """
    """

    def __init__(self, G, I1g=Is(0), V2g=Vs(0)):

        if issubclass(G.__class__, TwoPortGModel):
            G, I1g, V2g = G._M, G._I1g, G._V2g

        if not isinstance(G, GMatrix):
            raise ValueError('G not GMatrix')

        if not isinstance(I1g, Is):
            raise ValueError('I1g not Is')

        if not isinstance(V2g, Vs):
            raise ValueError('V2g not Vs')

        super(TwoPortGModel, self).__init__()
        self._M = G
        self._V1g = I1g
        self._I2g = V2g

    @property
    def G(self):
        """Return hybrid matrix"""
        return self._M

    @property
    def V2b(self):
        """Return V2b"""

        # FIXME
        return Vs(self.I1g / self.G.G12)

    @property
    def I2b(self):
        """Return I2b"""

        # FIXME
        return Is(self.G.G22 / self.G.G12 * self.I1g) - self.V2g

    @property
    def I1g(self):
        return self._V1g

    @property
    def V2g(self):
        return self._I2g


class TwoPortHModel(TwoPort):

    """
    ::
         +------+   +-------------------+
     I1  | +  - |   |                   | I2'          I2
    -->--+  V1h +---+                   +-<-------+-----<--
         |      |   |    two-port       |         |
    +    +------+   |    network        | +       |       +
    V1              |    without        | V2' ---+---+  V2
    -               |    sources        | -  |   |   |   -
                    |    represented    |    |  I2h  |
                    |    by H matrix    |    |   v   |
                    |                   |    +---+---+
                    |                   |        |
    ----------------+                   +--------+--------
                    |                   |
                    +-------------------+


    +-   +     +-        -+   +-  -+     +-   -+
    | V1 |  =  | H11  H12 |   | I1 |  +  | V1h |
    | I2 |     | H21  H22 |   | V2 |     | I2h |
    +-  -+     +-        -+   +-  -+     +-   -+
    """

    def __init__(self, H, V1h=Vs(0), I2h=Is(0)):

        if issubclass(H.__class__, TwoPortHModel):
            H, V1h, I2h = H._M, H._V1h, H._I2h

        if not isinstance(H, HMatrix):
            raise ValueError('H not HMatrix')

        if not isinstance(V1h, Vs):
            raise ValueError('V1h not Vs')

        if not isinstance(I2h, Is):
            raise ValueError('I2h not Is')

        super(TwoPortHModel, self).__init__()
        self._M = H
        self._V1h = V1h
        self._I2h = I2h

    @property
    def H(self):
        """Return hybrid matrix"""
        return self._M

    @property
    def V2b(self):
        """Return V2b"""

        return Vs(self.V1h / self.H.H12)

    @property
    def I2b(self):
        """Return I2b"""

        return Is(self.H.H22 / self.H.H12 * self.V1h) - self.I2h

    @property
    def V1h(self):
        return self._V1h

    @property
    def I2h(self):
        return self._I2h


class TwoPortYModel(TwoPort):

    """
    ::
                     +-------------------+
     I1              |                   | I2'           I2
    -->----+---------+                   +-<-------+-----<--
           |         |    two-port       |         |
    +      |       + |    network        | +       +       +
    V1 +---+---+  V1'|    without        | V2' +---+---+  V2
    -  |   |   |   - |    sources        | -   |   |   |   -
       |  I1y  |     |    represented    |     |  I2y  |
       |   v   |     |    by Y matrix    |     |   v   |
       +---+---+     |                   |     +---+---+
           |         |                   |         |
    -------+---------+                   +---------+--------
                     |                   |
                     +-------------------+

    +-   +     +-        -+   +-  -+     +-   -+
    | I1 |  =  | Y11  Y12 |   | V1 |  +  | I1y |
    | I2 |     | Y21  Y22 |   | V2 |     | I2y |
    +-  -+     +-        -+   +-  -+     +-   -+

    Ymn = Im / Vn for Vm = 0
    """

    def __init__(self, Y, I1y=Is(0), I2y=Is(0)):

        if issubclass(Y.__class__, TwoPortYModel):
            Y, I1y, I2y = Y._M, Y._I1y, Y._I2y

        if not isinstance(Y, YMatrix):
            raise ValueError('Y not YMatrix')

        if not isinstance(I1y, Is):
            raise ValueError('I1y not Is')
        if not isinstance(I2y, Is):
            raise ValueError('I2y not Is')

        super(TwoPortYModel, self).__init__()
        self._M = Y
        self._I1y = I1y
        self._I2y = I2y

    @property
    def Y(self):
        """Return admittance matrix"""
        return self._M

    @property
    def I2b(self):
        return Is(-self.I1y * self.Y11 * self.Y22 / self.Y12) - self.I2y

    @property
    def V2b(self):
        return Vs(self.I1y * self.Y11 / self.Y22)

    @property
    def I1y(self):
        return self._I1y

    @property
    def I2y(self):
        return self._I2y


class TwoPortZModel(TwoPort):

    """
    ::
         +------+    +-------------------+    +------+
    I1   | +  - | I1'|                   | I2'| -  + |  I2
    -->--+  V1z +-->-+                   +-<--+  V2z +--<--
         |      |    |    two-port       |    |      |
    +    +------+  + |    network        | +  +------+    +
    V1            V1'|    without        | V2'           V2
    -              - |    sources        | -              -
                     |    represented    |
                     |    by Z matrix    |
                     |                   |
                     |                   |
    -----------------+                   +-----------------
                     |                   |
                     +-------------------+

    +-   +     +-        -+   +-  -+     +-   -+
    | V1 |  =  | Z11  Z12 |   | I1 |  +  | V1z |
    | V2 |     | Z21  Z22 |   | I2 |     | V2z |
    +-  -+     +-        -+   +-  -+     +-   -+

    """

    def __init__(self, Z, V1z=Vs(0), V2z=Vs(0)):

        if issubclass(Z.__class__, TwoPortZModel):
            Z, V1z, V2z = Z._M, Z._V1z, Z._V2z

        if not isinstance(Z, ZMatrix):
            raise ValueError('Z not ZMatrix')

        if not isinstance(V1z, Vs):
            raise ValueError('V1z not Vs')
        if not isinstance(V2z, Vs):
            raise ValueError('V2z not Vs')

        super(TwoPortZModel, self).__init__()
        self._M = Z
        self._V1z = V1z
        self._V2z = V2z

    @property
    def Z(self):
        """Return impedance matrix"""
        return self._M

    @property
    def I2b(self):
        return Is(self.V1z / self.Z12)

    @property
    def V2b(self):
        return self.V2z - Vs(self.V1z * self.Z22 / self.Z12)

    @property
    def I1y(self):

        Zdet = self.Z.det()
        return Is(-self.V1z * self.Z22 / Zdet - self.V2z * self.Z12 / Zdet)

    @property
    def I2y(self):

        Zdet = self.Z.det()
        return Is(self.V1z * self.Z21 / Zdet - self.V2z * self.Z11 / Zdet)

    @property
    def V1z(self):
        return self._V1z

    @property
    def V2z(self):
        return self._V2z


class Chain(TwoPortBModel):

    """Connect two-port networks in a chain (aka cascade)"""

    def __init__(self, *args):

        self.args = args
        self._check_twoport_args()

        arg1 = args[-1]
        B = arg1.B

        foo = Vector(arg1.V2b, arg1.I2b)

        for arg in reversed(args[0:-1]):

            foo += B * Vector(arg.V2b, arg.I2b)
            B = B * arg.B

        super(Chain, self).__init__(B, Vs(foo[0, 0]), Is(foo[1, 0]))

    def simplify(self):

        if isinstance(self.args[0], Shunt) and isinstance(self.args[1], Shunt):
            return Shunt(
                (self.args[0].args[0] | self.args[1].args[0]).simplify())

        if isinstance(self.args[0], Series) and isinstance(
                self.args[1], Series):
            return Series(
                (self.args[0].args[0] + self.args[1].args[0]).simplify())

        return self


class Par2(TwoPortYModel):

    """Connect two-port networks in parallel"""

    def __init__(self, *args):

        self.args = args
        self._check_twoport_args()

        # This will fail with a Shunt as an argument since it does
        # not have a valid Y model.
        # We can special case this.
        if isinstance(args[0], Shunt) or isinstance(args[1], Shunt):
            print('Warning: need to handle a Shunt in parallel')

        arg = args[0]
        I1y = arg.I1y
        I2y = arg.I2y
        Y = arg.Y

        for arg in args[1:]:
            I1y += arg.I1y
            I2y += arg.I2y
            Y += arg.Y

        super(Par2, self).__init__(Y, I1y, I2y)

    def simplify(self):

        if isinstance(self.args[0], Shunt) and isinstance(self.args[1], Shunt):
            return Shunt(
                (self.args[0].args[0] | self.args[1].args[0]).simplify())

        if isinstance(self.args[0], Series) and isinstance(
                self.args[1], Series):
            return Series(
                (self.args[0].args[0] | self.args[1].args[0]).simplify())

        return self


class Ser2(TwoPortZModel):

    """Connect two-port networks in series (note this is unusual and can
    break the port condition)"""

    def __init__(self, *args):

        self.args = args
        self._check_twoport_args()

        # Need to be more rigorous.
        if isinstance(self.args[1], (Series, LSection, TSection)):
            print('Warning: This can violate the port condition')

        arg = args[0]
        V1z = arg.V1z
        V2z = arg.V2z
        Z = arg.Z

        for arg in args[1:]:
            V1z += arg.V1z
            V2z += arg.V2z
            Z += arg.Z

        super(Ser2, self).__init__(Z, V1z, V2z)

    def simplify(self):

        if isinstance(self.args[0], Shunt) and isinstance(self.args[1], Shunt):
            return Shunt(
                (self.args[0].args[0] + self.args[1].args[0]).simplify())

        return self


class Hybrid2(TwoPortHModel):

    """Connect two-port networks in hybrid configuration (inputs in
    series, outputs in parallel)"""

    def __init__(self, *args):

        self.args = args
        self._check_twoport_args()

        arg = args[0]
        V1h = arg.V1h
        I2h = arg.I2h
        H = arg.H

        for arg in args[1:]:
            V1h += arg.V1h
            I2h += arg.I2h
            H += arg.H

        super(Hybrid2, self).__init__(H, V1h, I2h)


class InverseHybrid2(TwoPortGModel):

    """Connect two-port networks in inverse hybrid configuration (outputs in
    series, inputs in parallel)"""

    def __init__(self, *args):

        self.args = args
        self._check_twoport_args()

        arg = args[0]
        I1g = arg.I1g
        V2g = arg.V2g
        G = arg.G

        for arg in args[1:]:
            I1g += arg.I1g
            V2g += arg.V2g
            G += arg.G

        super(Hybrid2, self).__init__(G, I1g, V2g)


class Series(TwoPortBModel):

    """
    Two-port comprising a single one-port in series configuration
    ::

           +---------+
         --+   OP    +---
           +---------+

         ----------------

    Note, this has a singular Y matrix.
    """

    def __init__(self, OP):

        self.OP = OP
        self.args = (OP, )
        _check_oneport_args(self.args)
        super(Series, self).__init__(BMatrix.Zseries(OP.Z), Vs(OP.Voc), Is(0))


class Shunt(TwoPortBModel):

    """
    Two-port comprising a single one-port in shunt configuration
    ::

         -----+----
              |
            +-+-+
            |   |
            |OP |
            |   |
            +-+-+
              |
         -----+----

    Note, this has a singular Z matrix.
    """

    def __init__(self, OP):

        self.OP = OP
        self.args = (OP, )
        _check_oneport_args(self.args)
        super(Shunt, self).__init__(BMatrix.Yshunt(OP.Y), Vs(0), Is(OP.Isc))


class IdealTransformer(TwoPortBModel):

    """Ideal transformer voltage gain alpha, current gain 1 / alpha"""

    def __init__(self, alpha=1):

        self.alpha = cExpr(alpha)
        self.args = (alpha, )
        super(IdealTransformer, self).__init__(BMatrix.transformer(alpha))


class TF(IdealTransformer):
    pass


class IdealGyrator(TwoPortBModel):

    """Ideal gyrator with gyration resistance R.

    A gyrator converts a voltage to current and a current to voltage.
    Cascaded gyrators act like a transformer"""

    def __init__(self, R=1):

        self.R = cExpr(R)
        self.args = (R, )
        super(IdealGyrator, self).__init__(BMatrix.gyrator(R))


class VoltageFollower(TwoPortBModel):

    """Voltage follower"""

    def __init__(self):

        self.args = ()
        super(VoltageFollower, self).__init__(BMatrix.voltage_amplifier(1))


class VoltageAmplifier(TwoPortBModel):

    """Voltage amplifier"""

    def __init__(self, Av=1, Af=0, Yin=0, Zout=0):

        Av = sExpr(Av)
        Af = sExpr(Af)
        Yin = sExpr(Yin)
        Zout = sExpr(Zout)

        self.args = (Av, Af, Yin, Zout)
        super(VoltageAmplifier, self).__init__(
            BMatrix.voltage_amplifier(Av, Af, Yin, Zout))


class IdealVoltageAmplifier(VoltageAmplifier):

    """Ideal voltage amplifier"""

    def __init__(self, Av=1):

        Av = sExpr(Av)
        super(IdealVoltageAmplifier, self).__init__(
            BMatrix.voltage_differentiator(Av))
        self.args = (Av, )


class IdealDelay(TwoPortBModel):

    """Ideal buffered delay"""

    def __init__(self, delay=0):

        delay = cExpr(delay)
        super(IdealDelay, self).__init__(
            BMatrix.voltage_amplifier(sym.exp(-s * delay)))
        self.args = (delay, )


class IdealVoltageDifferentiator(TwoPortBModel):

    """Voltage differentiator"""

    def __init__(self, Av=1):

        Av = sExpr(Av)
        super(IdealVoltageDifferentiator, self).__init__(
            BMatrix.voltage_differentiator(Av))
        self.args = (Av, )


class IdealVoltageIntegrator(TwoPortBModel):

    """Ideal voltage integrator"""

    def __init__(self, Av=1):

        Av = sExpr(Av)
        super(IdealVoltageIntegrator, self).__init__(
            BMatrix.voltage_integrator(Av))
        self.args = (Av, )


class CurrentFollower(TwoPortBModel):

    """Current follower"""

    def __init__(self):

        super(CurrentFollower, self).__init__(BMatrix.current_amplifier(1))
        self.args = ()


class IdealCurrentAmplifier(TwoPortBModel):

    """Ideal Current amplifier"""

    def __init__(self, Ai=1):

        Ai = sExpr(Ai)
        super(IdealCurrentAmplifier, self).__init__(
            BMatrix.current_amplifier(Ai))
        self.args = (Ai, )


class IdealCurrentDifferentiator(TwoPortBModel):

    """Ideal Current differentiator"""

    def __init__(self, Ai=1):

        Ai = sExpr(Ai)
        super(IdealCurrentDifferentiator, self).__init__(
            BMatrix.current_differentiator(Ai))
        self.args = (Ai, )


class IdealCurrentIntegrator(TwoPortBModel):

    """Ideal Current integrator"""

    def __init__(self, Ai=1):

        Ai = sExpr(Ai)
        super(IdealCurrentIntegrator, self).__init__(
            BMatrix.current_integrator(Ai))
        self.args = (Ai, )


class OpampInverter(TwoPortBModel):

    """Opamp inverter"""

    def __init__(self, R1, R2):

        R1 = cExpr(R1)
        R2 = cExpr(R2)
        # FIXME for initial voltages.
        super(OpampInverter, self).__init__(
            AMatrix(-R1.Z / R2.Z, 0, -1 / R2.Z, 0).B)
        self.args = (R1, R2)


class OpampIntegrator(TwoPortBModel):

    """Inverting opamp integrator"""

    def __init__(self, R1, C1):

        R1 = cExpr(R1)
        C1 = cExpr(C1)
        # FIXME for initial voltages.
        super(OpampIntegrator, self).__init__(
            AMatrix(-R1.Z / C1.Z, 0, -1 / C1.Z, 0).B)
        self.args = (R1, C1)


class OpampDifferentiator(TwoPortBModel):

    """Inverting opamp differentiator"""

    def __init__(self, R1, C1):

        R1 = cExpr(R1)
        C1 = cExpr(C1)
        # FIXME for initial voltages.
        super(OpampDifferentiator, self).__init__(
            AMatrix(-R1.Z * C1.Z, 0, -R1.Z, 0).B)
        self.args = (R1, C1)


class TSection(TwoPortBModel):

    """T (Y) section
    ::

           +---------+       +---------+
         --+   OP1   +---+---+   OP3   +---
           +---------+   |   +---------+
                       +-+-+
                       |   |
                       |OP2|
                       |   |
                       +-+-+
                         |
         ----------------+-----------------

      The Z matrix for a resistive T section is
      [ R1 + R2, R2     ]
      [      R2, R2 + R3]
    """

    def __init__(self, OP1, OP2, OP3):

        self.args = (OP1, OP2, OP3)
        _check_oneport_args(self.args)
        super(TSection, self).__init__(
            Series(OP1).chain(Shunt(OP2)).chain(Series(OP3)))

    def Pisection(self):

        ZV = WyeDelta(self.args[0].Z, self.args[1].Z, self.args[2].Z)
        VV = WyeDelta(self.args[0].V, self.args[1].V, self.args[2].V)
        OPV = [Thevenin(*OP).cpt() for OP in zip(ZV, VV)]

        return PiSection(*OPV)


class TwinTSection(TwoPortBModel):

    """Twin T section
    ::

              +---------+       +---------+
           +--+   OP1a  +---+---+   OP3a  +--+
           |  +---------+   |   +---------+  |
           |              +-+-+              |
           |              |   |              |
           |              |OP2a              |
           |              |   |              |
           |              +-+-+              |
           |                |                |
           |                v                |
           |  +---------+       +---------+  |
         --+--+   OP1b  +---+---+   OP3b  +--+--
              +---------+   |   +---------+
                          +-+-+
                          |   |
                          |OP2b
                          |   |
                          +-+-+
                            |
         -------------------+--------------------

    """

    def __init__(self, OP1a, OP2a, OP3a, OP1b, OP2b, OP3b):

        self.args = (OP1a, OP2a, OP3a, OP1b, OP2b, OP3b)
        _check_oneport_args(self.args)

        super(TwinTSection, self).__init__(
            TSection(OP1a, OP2a, OP3a).parallel(TSection(OP1b, OP2b, OP3b)))


class BridgedTSection(TwoPortBModel):

    """Bridged T section
        ::

                       +---------+
           +-----------+   OP4   +-----------+
           |           +---------+           |
           |                                 |
           |  +---------+       +---------+  |
         --+--+   OP1b  +---+---+   OP3b  +--+--
              +---------+   |   +---------+
                          +-+-+
                          |   |
                          |OP2b
                          |   |
                          +-+-+
                            |
         -------------------+--------------------

         """

    def __init__(self, OP1, OP2, OP3, OP4):

        self.args = (OP1, OP2, OP3, OP4)
        _check_oneport_args(self.args)

        super(TwinTSection, self).__init__(
            TSection(OP1, OP2, OP3).parallel(Series(OP4)))


class PiSection(TwoPortBModel):

    """Pi (delta) section
    ::

                  +---------+
        -----+----+   OP2    +---+-----
             |    +---------+   |
           +-+-+              +-+-+
           |   |              |   |
           |OP1|              |OP3|
           |   |              |   |
           +-+-+              +-+-+
             |                  |
        -----+------------------+-----

    """

    def __init__(self, OP1, OP2, OP3):

        super(PiSection, self).__init__(
            Shunt(OP1).chain(Series(OP2)).chain(Shunt(OP3)))
        self.args = (OP1, OP2, OP3)

    def Tsection(self):

        ZV = DeltaWye(self.args[0].Z, self.args[1].Z, self.args[2].Z)
        VV = DeltaWye(self.args[0].V, self.args[1].V, self.args[2].V)
        OPV = [Thevenin(OP[0], OP[1]).cpt() for OP in zip(ZV, VV)]
        return TSection(*OPV)


class LSection(TwoPortBModel):

    """L Section
    ::

           +---------+
         --+   OP1   +---+----
           +---------+   |
                       +-+-+
                       |   |
                       |OP2|
                       |   |
                       +-+-+
                         |
         ----------------+----
    """

    def __init__(self, OP1, OP2):

        self.args = (OP1, OP2)
        _check_oneport_args(self.args)

        super(LSection, self).__init__(Series(OP1).chain(Shunt(OP2)))


class Ladder(TwoPortBModel):

    """(Unbalanced) ladder network with alternating Series and Shunt
    networks chained
    ::

           +---------+       +---------+
         --+   OP1   +---+---+ args[1] +---
           +---------+   |   +---------+
                       +-+-+
                       |   |
                       |   | args[0]
                       |   |
                       +-+-+
                         |
         ----------------+-----------------
    """

    def __init__(self, OP1, *args):

        self.args = (OP1, ) + args
        _check_oneport_args(self.args)

        TP = Series(OP1)

        for m, arg in enumerate(args):

            if m & 1:
                TP = TP.chain(Series(arg))
            else:
                TP = TP.chain(Shunt(arg))

        super(Ladder, self).__init__(TP)

    def simplify(self):

        if len(self.args) == 1:
            return Series(self.args[0])
        elif len(self.args) == 2:
            return LSection(*self.args)
        elif len(self.args) == 3:
            return TSection(*self.args)
        return self

        # A Ladder of voltage sources and current sources
        # collapses to a single Lsection comprised of the total
        # voltage and total current.


class GeneralTxLine(TwoPortBModel):

    """General transmission line

    Z0 is the (real) characteristic impedance (ohms)
    gamma is the propagation constant (1/m)
    l is the transmission line length (m)
    """

    def __init__(self, Z0, gamma, l):

        Z0 = sExpr(Z0)
        gamma = sExpr(gamma)
        l = cExpr(l)

        H = sym.exp(gamma * l)

        B11 = 0.5 * (H + 1 / H)
        B12 = 0.5 * (1 / H - H) * Z0
        B21 = 0.5 * (1 / H - H) / Z0
        B22 = 0.5 * (H + 1 / H)

        super(GeneralTxLine, self).__init__(BMatrix(B11, B12, B21, B22))
        self.args = (Z0, gamma, l)


class LosslessTxLine(GeneralTxLine):

    """Losslees transmission line
        Z0 is the (real) characteristic impedance (ohms)
        c is the propagation speed (m/s)
        l is the transmission line length (m)
        """

    def __init__(self, Z0, c=1.5e8, l=1):

        gamma = s / c

        super(LosslessTxLine, self).__init__(Z0, gamma, l)


class TxLine(GeneralTxLine):

    """Transmission line

    R series resistance/metre
    L series inductance/metre
    G shunt conductance/metre
    C shunt capacitance/metre
    l is the transmission line length
    """

    def __init__(self, R, L, G, C, l=1):

        Z = R + s * L
        Y = G + s * C
        gamma = sym.sqrt(Z * Y)
        Z0 = sym.sqrt(Z / Y)

        super(TxLine, self).__init__(Z0, gamma, l)
