"""
This module supports simple linear one-port networks based on the
following ideal components:

V independent voltage source
I independent current source
R resistor
C capacitor
L inductor

These components are converted to s-domain models and so capacitor and
inductor components can be specified with initial voltage and
currents, respectively, to model transient responses.

The components are represented by either Thevenin or Norton one-port
networks with the following attributes:

Zoc open-circuit impedance
Ysc short-circuit admittance
Voc open-circuit voltage
Isc short-circuit current

One-ports can either be connected in series (+) or parallel (|) to
create a new one-port.

Copyright 2014, 2015, 2016 Michael Hayes, UCECE
"""

from __future__ import division
import sympy as sym
from lcapy.core import t, s, Vs, Is, Zs, Ys, cExpr, sExpr, tExpr, tsExpr, cos, exp, symbol, j, Vphasor, Iphasor, It, Itype, Vtype, pretty
from lcapy.sympify import symbols_find
from lcapy.network import Network


__all__ = ('V', 'I', 'v', 'i', 'R', 'L', 'C', 'G', 'Y', 'Z',
           'Vdc', 'Vstep', 'Idc', 'Istep', 'Vac', 'sV', 'sI',
           'Iac', 'Norton', 'Thevenin',
           'Par', 'Ser', 'Xtal', 'FerriteBead')

def _check_oneport_args(args):

    for arg1 in args:
        if not isinstance(arg1, OnePort):
            raise ValueError('%s not a OnePort' % arg1)


class OnePort(Network):
    """One-port network

    There are three types of OnePort: ParSer (for combinations of 
    OnePort), Thevenin, and Norton.

    Attributes: Y, Z, Voc, Isc, y, z, voc, isc
    """

    # Dimensions and separations of component with horizontal orientation.
    height = 0.3
    hsep = 0.5
    width = 1
    wsep = 0.5

    netname = ''
    netkeyword = ''

    def __add__(self, OP):
        """Series combination"""

        return Ser(self, OP)

    def __or__(self, OP):
        """Parallel combination"""

        return Par(self, OP)

    def series(self, OP):
        """Series combination"""

        return Ser(self, OP)

    def parallel(self, OP):
        """Parallel combination"""

        return Par(self, OP)

    @property
    def Zoc(self):
        return self.Z

    @property
    def Ysc(self):
        return self.Y

    def ladder(self, *args):
        """Create (unbalanced) ladder network"""

        return Ladder(self, *args)

    def lsection(self, OP2):
        """Create L section (voltage divider)"""

        if not issubclass(OP2.__class__, OnePort):
            raise TypeError('Argument not ', OnePort)

        return LSection(self, OP2)

    def tsection(self, OP2, OP3):
        """Create T section"""

        if not issubclass(OP2.__class__, OnePort):
            raise TypeError('Argument not ', OnePort)

        if not issubclass(OP3.__class__, OnePort):
            raise TypeError('Argument not ', OnePort)

        return TSection(self, OP2, OP3)

    def expand(self):

        return self

    def smodel(self):
        """Convert to s-domain"""
        raise NotImplemented('smodel not implemented')

    @property
    def voc(self):
        return self.Voc.time()

    @property
    def isc(self):
        return self.Isc.time()

    @property
    def y(self):
        return self.Y.time()

    @property
    def z(self):
        return self.Z.time()

    @property
    def I(self):
        return Is(0)

    @property
    def i(self):
        return It(0)

    @property
    def V(self):
        self._solve()
        return self._V[1]

    @property
    def v(self):
        return self.V.time()

    @property
    def Y(self):
        return self._Y

    @Y.setter
    def Y(self, val):
        self._Y = val

    @property
    def Z(self):
        return self._Z

    @Z.setter
    def Z(self, val):
        self._Z = val

    def thevenin(self):
        """Simplify to a Thevenin network"""

        # FIXME,  This jumps into the s-domain if have a combination of
        # components.

        if self.Y == 0:
            print('Dodgy Norton to Thevenin transformation since Y = 0')

        Z1 = self.Z.cpt()
        V1 = self.Voc.cpt()

        if not isinstance(V1, OnePort):
            V1 = V(V1)

        if self.is_dc:
            Z1 = Z1.Z.real
            if not isinstance(Z1, OnePort):
                Z1 = R(Z1)

        if not isinstance(Z1, OnePort):
            Z1 = Z(Z1)

        if V1.Voc == 0:
            return Z1
        if Z1.Z == 0:
            return V1

        return Ser(Z1, V1)

    def norton(self):
        """Simplify to a Norton network"""

        # FIXME,  This jumps into the s-domain if have a combination of
        # components.

        if self.Z == 0:
            print('Dodgy Thevenin to Norton transformation since Z = 0')

        Y1 = self.Y.cpt()
        I1 = self.Isc.cpt()

        if not isinstance(I1, OnePort):
            I1 = I(I1)

        if self.is_dc:
            Y1 = Y1.Y.real
            if not isinstance(Y1, OnePort):
                Y1 = G(Y1)

        if I1.Isc == 0:
            return Y1
        if Y1.Y == 0:
            return I1

        return Par(Y1, I1)

    def smodel(self):
        """Convert to s-domain"""
        args = [arg.smodel() for arg in self.args]
        return (self.__class__(*args))


class ParSer(OnePort):
    """Parallel/serial class"""

    def __str__(self):

        str = ''

        for m, arg in enumerate(self.args):
            argstr = arg.__str__()

            if isinstance(arg, ParSer) and arg.__class__ != self.__class__:
                argstr = '(' + argstr + ')'

            str += argstr

            if m != len(self.args) - 1:
                str += ' %s ' % self._operator

        return str

    def _repr_pretty_(self, p, cycle):

        p.text(self.pretty())

    def _repr_latex_(self):

        return '$%s$' % self.latex()

    def pretty(self):

        str = ''

        for m, arg in enumerate(self.args):
            argstr = arg.pretty()

            if isinstance(arg, ParSer) and arg.__class__ != self.__class__:
                argstr = '(' + argstr + ')'

            str += argstr

            if m != len(self.args) - 1:
                str += ' %s ' % self._operator

        return str

    def pprint(self):

        print(self.pretty())

    def latex(self):

        str = ''

        for m, arg in enumerate(self.args):
            argstr = arg.latex()

            if isinstance(arg, ParSer) and arg.__class__ != self.__class__:
                argstr = '(' + argstr + ')'

            str += argstr

            if m != len(self.args) - 1:
                str += ' %s ' % self._operator

        return str

    def _combine(self, arg1, arg2):

        if arg1.__class__ != arg2.__class__:
            if self.__class__ == Ser:
                if isinstance(arg1, V) and arg1.Voc == 0:
                    return arg2
                if isinstance(arg2, V) and arg2.Voc == 0:
                    return arg1
                if isinstance(arg1, Z) and arg1.Z == 0:
                    return arg2
                if isinstance(arg2, Z) and arg2.Z == 0:
                    return arg1
            if self.__class__ == Par:
                if isinstance(arg1, I) and arg1.Isc == 0:
                    return arg2
                if isinstance(arg2, I) and arg2.Isc == 0:
                    return arg1
                if isinstance(arg1, Y) and arg1.Y == 0:
                    return arg2
                if isinstance(arg2, Y) and arg2.Y == 0:
                    return arg1

            return None

        if self.__class__ == Ser:
            if isinstance(arg1, I):
                return None
            if isinstance(arg1, Vdc):
                return Vdc(arg1.v0 + arg2.v0)
            # Could simplify Vac here if same frequency
            if isinstance(arg1, V):
                return V(arg1 + arg2)
            if isinstance(arg1, R):
                return R(arg1.R + arg2.R)
            if isinstance(arg1, L):
                # The currents should be the same!
                if arg1.i0 != arg2.i0:
                    raise ValueError('Series inductors with different'
                          ' initial currents!')
                return L(arg1.L + arg2.L, arg1.i0)
            if isinstance(arg1, G):
                return G(arg1.G * arg2.G / (arg1.G + arg2.G))
            if isinstance(arg1, C):
                return C(
                    arg1.C * arg2.C / (arg1.C + arg2.C), arg1.v0 + arg2.v0)
            return None

        elif self.__class__ == Par:
            if isinstance(arg1, V):
                return None
            if isinstance(arg1, Idc):
                return Idc(arg1.i0 + arg2.i0)
            # Could simplify Iac here if same frequency
            if isinstance(arg1, I):
                return I(arg1 + arg2)
            if isinstance(arg1, G):
                return G(arg1.G + arg2.G)
            if isinstance(arg1, C):
                # The voltages should be the same!
                if arg1.v0 != arg2.v0:
                    raise ValueError('Parallel capacitors with different'
                          ' initial voltages!')
                return C(arg1.C + arg2.C, arg1.v0)
            if isinstance(arg1, R):
                return R(arg1.R * arg2.R / (arg1.R + arg2.R))
            if isinstance(arg1, L):
                return L(
                    arg1.L * arg2.L / (arg1.L + arg2.L), arg1.i0 + arg2.i0)
            return None

        else:
            raise TypeError('Undefined class')

    def simplify(self, deep=True):
        """Perform simple simplifications, such as parallel resistors,
        series inductors, etc., rather than collapsing to a Thevenin
        or Norton network.

        This does not expand compound components such as crystal
        or ferrite bead models.  Use expand() first.
        """

        # Simplify args (recursively) and combine operators if have
        # Par(Par(A, B), C) etc.
        new = False
        newargs = []
        for m, arg in enumerate(self.args):
            if isinstance(arg, ParSer):
                arg = arg.simplify(deep)
                new = True
                if arg.__class__ == self.__class__:
                    newargs.extend(arg.args)
                else:
                    newargs.append(arg)
            else:
                newargs.append(arg)

        if new:
            self = self.__class__(*newargs)

        # Scan arg list looking for compatible combinations.
        # Could special case the common case of two args.
        new = False
        args = list(self.args)
        for n in range(len(args)):

            arg1 = args[n]
            if arg1 is None:
                continue
            if isinstance(arg1, ParSer):
                continue

            for m in range(n + 1, len(args)):

                arg2 = args[m]
                if arg2 is None:
                    continue
                if isinstance(arg2, ParSer):
                    continue

                # TODO, think how to simplify things such as
                # Par(Ser(V1, R1), Ser(R2, V2)).
                # Could do Thevenin/Norton transformations.

                newarg = self._combine(arg1, arg2)
                if newarg is not None:
                    # print('Combining', arg1, arg2, 'to', newarg)
                    args[m] = None
                    arg1 = newarg
                    new = True

            args[n] = arg1

        if new:
            args = [arg for arg in args if arg is not None]
            if len(args) == 1:
                return args[0]
            self = self.__class__(*args)

        return self

    def expand(self):
        """Expand compound components such as crystals or ferrite bead
        models into R, L, G, C, V, I"""

        newargs = []
        for m, arg in enumerate(self.args):
            newarg = arg.expand()
            newargs.append(newarg)

        return self.__class__(*newargs)

    def smodel(self):
        """Convert to s-domain"""
        args = [arg.smodel() for arg in self.args]
        return (self.__class__(*args))

    @property
    def Isc(self):

        Voc = self.Voc
        Z = self.Z
        assumptions = Voc.assumptions
        return Itype(Voc / Z, **assumptions)

    @property
    def Voc(self):
        self._solve()
        Voc = self._V[1]
        # FIXME
        assumptions = self._V.assumptions
        return Vtype(Voc, **assumptions)

    @property
    def Y(self):
        # Could extract directly if have Y || I or Z + V
        return self.admittance(1, 0)

    @property
    def Z(self):
        # Could extract directly if have Y || I or Z + V
        return self.impedance(1, 0)

class Par(ParSer):
    """Parallel class"""

    _operator = '|'

    def __init__(self, *args):

        _check_oneport_args(args)
        super(Par, self).__init__()
        self.args = args

        for n, arg1 in enumerate(self.args):
            for arg2 in self.args[n + 1:]:
                if isinstance(arg1, V) and isinstance(arg2, V):
                    raise ValueError('Voltage sources connected in parallel'
                                     ' %s and %s' % (arg1, arg2))
                if isinstance(arg1, V) or isinstance(arg2, V):
                    # Should simplify by removing redundant component to
                    # save later grief with Norton or Thevenin transformation.
                    print('Warn: parallel connection with voltage source:'
                          ' %s and %s' % (arg1, arg2))

    @property
    def width(self):

        total = 0
        for arg in self.args:
            val = arg.width
            if val > total:
                total = val
        return total + 2 * self.wsep

    @property
    def height(self):

        total = 0
        for arg in self.args:
            total += arg.height
        return total + (len(self.args) - 1) * self.hsep

    def net_make(self, net, n1=None, n2=None):

        s = []
        if n1 is None:
            n1 = net.node
        n3, n4 =  net.node, net.node

        H = [(arg.height + self.hsep) * 0.5 for arg in self.args]
        
        N = len(H)
        num_branches = N // 2

        # Draw component in centre if have odd number in parallel.
        if (N & 1):
            s.append(self.args[N // 2].net_make(net, n3, n4))

        na, nb = n3, n4

        s.append('W %s %s; right=%s' % (n1, n3, self.wsep))

        # Draw components above centre
        for n in range(num_branches):

            if not (N & 1) and n == 0:
                sep = H[N // 2 - 1]
            else:
                sep = H[N // 2 - n] + H[N // 2 - 1 - n]

            nc, nd =  net.node, net.node
            s.append('W %s %s; up=%s' % (na, nc, sep))
            s.append('W %s %s; up=%s' % (nb, nd, sep))
            s.append(self.args[N // 2 - 1 - n].net_make(net, nc, nd))
            na, nb = nc, nd

        na, nb = n3, n4

        # Draw components below centre
        for n in range(num_branches):

            if not (N & 1) and n == 0:
                sep = H[(N + 1) // 2]
            else:
                sep = H[(N + 1) // 2 + n] + H[(N + 1) // 2 - 1 + n]

            nc, nd =  net.node, net.node
            s.append('W %s %s; down=%s' % (na, nc, sep))
            s.append('W %s %s; down=%s' % (nb, nd, sep))
            s.append(self.args[(N + 1) // 2 + n].net_make(net, nc, nd))
            na, nb = nc, nd

        if n2 is None:
            n2 = net.node

        s.append('W %s %s; right=%s' % (n4, n2, self.wsep))
        return '\n'.join(s)


class Ser(ParSer):
    """Series class"""

    _operator = '+'

    def __init__(self, *args):

        _check_oneport_args(args)
        super(Ser, self).__init__()
        self.args = args

        for n, arg1 in enumerate(self.args):
            for arg2 in self.args[n + 1:]:
                if isinstance(arg1, I) and isinstance(arg2, I):
                    raise ValueError('Current sources connected in series'
                                     ' %s and %s' % (arg1, arg2))
                if isinstance(arg1, I) or isinstance(arg2, I):
                    # Should simplify by removing redundant component to
                    # save later grief with Norton or Thevenin transformation.
                    print('Warn: series connection with current source:'
                          ' %s and %s' % (arg1, arg2))

    @property
    def height(self):

        total = 0
        for arg in self.args:
            val = arg.height
            if val > total:
                total = val
        return total

    @property
    def width(self):

        total = 0
        for arg in self.args:
            total += arg.width
        return total + (len(self.args) - 1) * self.wsep

    def net_make(self, net, n1=None, n2=None):

        s = []
        if n1 is None:
            n1 = net.node
        for arg in self.args[:-1]:
            n3 = net.node
            s.append(arg.net_make(net, n1, n3))
            n1 = net.node
            s.append('W %s %s; right=%s' % (n3, n1, self.wsep))

        if n2 is None:
            n2 = net.node
        s.append(self.args[-1].net_make(net, n1, n2))
        return '\n'.join(s)


class Norton(OnePort):
    """Norton (Y) model
    ::

                +-------------------+
        I1      |                   |      -I1
        -->-+---+        Y          +---+--<--
            |   |                   |   |
            |   +-------------------+   |
            |                           |
            |                           |
            |          +------+         |
            |          |      |         |
            +----------+ -I-> +---------+
                       |      |
                       +------+

          +              V1                 -
    """

    def __init__(self, Yval=Ys(0), Ival=Is(0)):

        # print('<N> Y:', Yval, 'I:', Ival)
        if not isinstance(Yval, Ys):
            raise ValueError('Yval not Ys')
        if not isinstance(Ival, Is):
            raise ValueError('Ival not Is')
        self.Y = Yval
        self.Isc = Ival

        super(Norton, self).__init__()

    @property
    def Z(self):
        return Zs(1 / self.Y)

    @property
    def Voc(self):
        return Vtype(self.Isc / self.Y, **self.Isc.assumptions)

    def cpt(self):
        """Convert to a component, if possible"""

        if self.Y.is_number and self.Isc == 0:
            return G(self.Y.expr)

        i = s * self.Isc
        if self.Y == 0 and i.is_number:
            return Idc(i.expr)

        v = s * self.Voc
        if self.Z == 0 and v.is_number:
            return Vdc(v.expr)

        y = s * self.Y
        z = s * self.Z

        if z.is_number and v.is_number:
            return C((1 / z).expr, v)

        if y.is_number and i.is_number:
            return L((1 / y).expr, i)

        if self.Isc == 0:
            return Y(self.Y.expr)

        return self

    def smodel(self):
        """Convert to s-domain"""

        if self.Isc == 0:
            return Y(self.Y)
        if self.Y == 0:
            return sI(self.Isc)
        return Par(sI(self.Isc), Y(self.Y))


class Thevenin(OnePort):
    """Thevenin (Z) model
    ::

             +------+    +-------------------+
        I1   | +  - |    |                   | -I1
        -->--+  V   +----+        Z          +--<--
             |      |    |                   |
             +------+    +-------------------+
        +                       V1                -
    """

    def __init__(self, Zval=Zs(0), Vval=Vs(0)):

        # print('<T> Z:', Zval, 'V:', Vval)
        if not isinstance(Zval, Zs):
            raise ValueError('Zval not Zs')
        if not isinstance(Vval, Vs):
            raise ValueError('Vval not Vs')
        self.Z = Zval
        self.Voc = Vval

        super(Thevenin, self).__init__()

    @property
    def Y(self):
        return Ys(1 / self.Z)

    @property
    def Isc(self):

        assumptions = self.Voc.assumptions
        return Itype(self.Voc / self.Z, **assumptions)

    def parallel_ladder(self, *args):
        """Add unbalanced ladder network in parallel;
        alternately in parallel and series.

        ::

               +---------+       +---------+
            +--+   self  +---+---+   Z1    +---+---
            |  +---------+   |   +---------+   |
            |              +-+-+             +-+-+
            |              |   |             |   |
            |              |Z0 |             |Z2 |
            |              |   |             |   |
            |              +-+-+             +-+-+
            |                |                 |
            +----------------+-----------------+---
        """

        ret = self
        for m, arg in enumerate(args):
            if m & 1:
                ret = ret.series(arg)
            else:
                ret = ret.parallel(arg)
        return ret

    def parallel_C(self, Z0, Z1, Z2):
        """Add C network in parallel.

        ::

               +---------+      +---------+
            +--+   self  +------+   Z0    +---+----
            |  +---------+      +---------+   |
            |                               +-+-+
            |                               |   |
            |                               |Z1 |
            |                               |   |
            |                               +-+-+
            |                   +---------+   |
            +-------------------+   Z2    +---+----
                                +---------+
        """

        return self.series(Z0).series(Z2).parallel(Z1)

    def parallel_L(self, Z0, Z1):
        """Add L network in parallel.

        ::

               +---------+      +---------+
            +--+   self  +------+   Z0    +---+----
            |  +---------+      +---------+   |
            |                               +-+-+
            |                               |   |
            |                               |Z1 |
            |                               |   |
            |                               +-+-+
            |                                 |
            +---------------------------------+----
        """

        return self.series(Z0).parallel(Z1)

    def parallel_pi(self, Z0, Z1, Z2):
        """Add Pi (Delta) network in parallel.

        ::

               +---------+       +---------+
            +--+   self  +---+---+   Z1    +---+---
            |  +---------+   |   +---------+   |
            |              +-+-+             +-+-+
            |              |   |             |   |
            |              |Z0 |             |Z2 |
            |              |   |             |   |
            |              +-+-+             +-+-+
            |                |                 |
            +----------------+-----------------+---
        """

        return (self.parallel(Z0) + Z1).parallel(Z2)

    def parallel_T(self, Z0, Z1, Z2):
        """Add T (Y) network in parallel.
        ::

               +---------+       +---------+        +---------+
            +--+   self  +-------+   Z0    +---+----+   Z2    +---
            |  +---------+       +---------+   |    +---------+
            |                                +-+-+
            |                                |   |
            |                                |Z1 |
            |                                |   |
            |                                +-+-+
            |                                  |
            +----------------------------------+------------------
        """

        return (self.parallel(Z0) + Z1).parallel(Z2)

    def cpt(self):
        """Convert to a component, if possible"""

        if self.Z.is_number and self.Voc == 0:
            return R(self.Z.expr)

        v = s * self.Voc
        if self.Z == 0 and v.is_number:
            return Vdc(v.expr)

        i = s * self.Isc
        if self.Y == 0 and i.is_number:
            return Idc(i.expr)

        y = s * self.Y
        z = s * self.Z

        if z.is_number and v.is_number:
            return C((1 / z).expr, v)

        if y.is_number and i.is_number:
            return L((1 / y).expr, i)

        if self.Voc == 0:
            return Z(self.Z.expr)

        return self

    def smodel(self):
        """Convert to s-domain"""

        if self.Voc == 0:
            return Z(self.Z)
        if self.Z == 0:
            return sV(self.Voc)
        return Ser(sV(self.Voc), Z(self.Z))


class R(Thevenin):
    """Resistor"""

    def __init__(self, Rval):

        self.args = (Rval, )
        Rval = cExpr(Rval, positive=True)
        super(R, self).__init__(Zs.R(Rval))
        self.R = Rval


class G(Norton):
    """Conductance"""

    def __init__(self, Gval):

        self.args = (Gval, )
        Gval = cExpr(Gval, positive=True)
        super(G, self).__init__(Ys.G(Gval))
        self.G = Gval

    def net_make(self, net, n1=None, n2=None):

        if n1 == None:
            n1 = net.node
        if n2 == None:
            n2 = net.node
        return 'R %s %s %s; right' % (n1, n2, 1 / self.G)


class L(Thevenin):
    """Inductor

    Inductance Lval, initial current i0"""

    def __init__(self, Lval, i0=None):

        self.hasic = i0 is not None
        if i0 is None:
            i0 = 0

        if self.hasic:
            self.args = (Lval, i0)
        else:
            self.args = (Lval, )

        Lval = cExpr(Lval, positive=True)
        i0 = cExpr(i0)
        super(L, self).__init__(Zs.L(Lval), -Vs(i0 * Lval))
        self.L = Lval
        self.i0 = i0
       
        self.zeroic = self.i0 == 0 


class C(Thevenin):
    """Capacitor

    Capacitance Cval, initial voltage v0"""

    def __init__(self, Cval, v0=None):

        self.hasic = v0 is not None
        if v0 is None:
            v0 = 0

        if self.hasic:
            self.args = (Cval, v0)
        else:
            self.args = (Cval, )

        Cval = cExpr(Cval, positive=True)
        v0 = cExpr(v0)
        super(C, self).__init__(Zs.C(Cval), Vs(v0).integrate())
        self.C = Cval
        self.v0 = v0

        self.zeroic = self.v0 == 0


class Y(Norton):
    """General admittance."""

    def __init__(self, Yval):

        self.args = (Yval, )
        Yval = Ys(Yval)
        super(Y, self).__init__(Yval)


class Z(Thevenin):
    """General impedance."""

    def __init__(self, Zval):

        self.args = (Zval, )
        Zval = Zs(Zval)
        super(Z, self).__init__(Zval)


class VoltageSource(Thevenin):

    voltage_source = True
    netname = 'V'

    def __init__(self, Vval):

        super(VoltageSource, self).__init__(Zs(0), Vs(Vval))


class sV(VoltageSource):
    """Arbitrary s-domain voltage source"""

    netkeyword = 's'

    def __init__(self, Vval):

        self.args = (Vval, )
        Vval = sExpr(Vval)
        super(sV, self).__init__(Vs(Vval))

    @property
    def Vocac(self):
        if not self.Voc.is_ac:
            raise ValueError('No ac representation for %s' % self)
        return self.Voc.phasor()

class V(VoltageSource):
    """Voltage source. If the expression contains s treat as s-domain
    voltage otherwise time domain.  A constant V is considered DC
    with an s-domain voltage V / s."""

    def __init__(self, Vval):

        self.args = (Vval, )
        Vsym = tsExpr(Vval)
        super(V, self).__init__(Vs(Vsym))

    @property
    def Vocac(self):
        if not self.Voc.is_ac:
            raise ValueError('No ac representation for %s' % self)
        return self.Voc.phasor()


class Vstep(VoltageSource):
    """Step voltage source (s domain voltage of v / s)."""

    netkeyword = 'step'

    def __init__(self, v):

        self.args = (v, )
        v = cExpr(v)
        super(Vstep, self).__init__(Vs(v, causal=True) / s)
        # This is not needed when assumptions propagated.
        self.Voc.is_causal = True
        self.v0 = v


class Vdc(VoltageSource):
    """DC voltage source (note a DC voltage source of voltage V has
    an s domain voltage of V / s)."""

    netkeyword = 'dc'
    
    def __init__(self, v):

        self.args = (v, )
        v = cExpr(v)
        super(Vdc, self).__init__(Vs(v, dc=True) / s)
        # This is not needed when assumptions propagated.
        self.Voc.is_dc = True
        self.v0 = v

    @property
    def voc(self):
        return self.v0


class Vac(VoltageSource):
    """AC voltage source."""

    netkeyword = 'ac'

    def __init__(self, V, phi=0):

        self.args = (V, phi)
        V = cExpr(V)
        phi = cExpr(phi)

        # Note, cos(-pi / 2) is not quite zero.

        self.omega = symbol('omega_1', real=True)
        foo = (s * sym.cos(phi) + self.omega * sym.sin(phi)) / (s**2 + self.omega**2)
        super(Vac, self).__init__(Vs(foo * V, ac=True))
        # This is not needed when assumptions propagated.
        self.Voc.is_ac = True
        self.v0 = V
        self.phi = phi


    @property
    def voc(self):
        return self.v0 * cos(self.omega * t + self.phi)

    @property
    def Vocac(self):
        return Vphasor(self.v0 * exp(j * self.phi))


class v(VoltageSource):
    """Arbitrary t-domain voltage source"""

    def __init__(self, vval):

        self.args = (vval, )
        Vval = tExpr(vval)
        super(V, self).__init__(Zs(0), Vs(Vval).laplace())
        self.assumptions_infer(Vval)


class CurrentSource(Norton):

    current_source = True
    netname = 'I'

    def __init__(self, Ival):

        super(CurrentSource, self).__init__(Ys(0), Is(Ival))


class sI(CurrentSource):
    """Arbitrary s-domain current source"""

    netkeyword = 's'

    def __init__(self, Ival):

        self.args = (Ival, )
        Ival = sExpr(Ival)
        super(sI, self).__init__(Ys(0), Is(Ival))

    @property
    def Iscac(self):
        if not self.Isc.is_ac:
            raise IalueError('No ac representation for %s' % self)
        return self.Isc.phasor()


class I(CurrentSource):
    """Current source. If the expression contains s treat as s-domain
    current otherwise time domain.  A constant I is considered DC with
    an s-domain current I / s.

    """

    def __init__(self, Ival):

        self.args = (Ival, )
        Isym = tsExpr(Ival)
        super(I, self).__init__(Is(Isym))

    @property
    def Iocac(self):
        if not self.Ioc.is_ac:
            raise ValueError('No ac representation for %s' % self)
        return self.Ioc.phasor()

class Istep(CurrentSource):
    """Step current source (s domain current of i / s)."""

    netkeyword = 'step'

    def __init__(self, i):

        self.args = (i, )
        i = cExpr(i)
        super(Istep, self).__init__(Is(i, causal=True) / s)
        # This is not needed when assumptions propagated.
        self.Isc.is_causal = True
        self.i0 = i


class Idc(CurrentSource):
    """DC current source (note a DC current source of current i has
    an s domain current of i / s)."""

    netkeyword = 'dc'
    
    def __init__(self, i):

        self.args = (i, )
        i = cExpr(i)
        super(Idc, self).__init__(Is(i, dc=True) / s)
        # This is not needed when assumptions propagated.
        self.Isc.is_dc = True
        self.i0 = i

    @property
    def isc(self):
        return self.i0

    @property
    def Iscac(self):
        return Iphasor(self.i0)


class Iac(CurrentSource):
    """AC current source."""

    netkeyword = 'ac'

    def __init__(self, I, phi=0):

        self.args = (I, phi)
        I = cExpr(I)
        phi = cExpr(phi)

        self.omega = symbol('omega_1', real=True)
        foo = (s * sym.cos(phi) + self.omega * sym.sin(phi)) / (s**2 + self.omega**2)
        super(Iac, self).__init__(Is(foo * I, ac=True))
        # This is not needed when assumptions propagated.
        self.Isc.is_ac = True
        self.i0 = I
        self.phi = phi

    @property
    def isc(self):
        return self.i0 * cos(self.omega * t + self.phi)

    @property
    def Iscac(self):
        return Iphasor(self.i0 * exp(j * self.phi))


class i(CurrentSource):
    """Arbitrary t-domain current source"""

    def __init__(self, ival):

        self.args = (ival, )
        Ival = tExpr(ival)
        super(I, self).__init__(Is(Ival.laplace()))
        self.assumptions_infer(Ival)


class Xtal(Thevenin):
    """Crystal

    This is modelled as a series R, L, C circuit in parallel
    with C0 (a Butterworth van Dyke model).  Note,
    harmonic resonances are not modelled.
    """

    def __init__(self, C0, R1, L1, C1):

        self.C0 = cExpr(C0, positive=True)
        self.R1 = cExpr(R1, positive=True)
        self.L1 = cExpr(L1, positive=True)
        self.C1 = cExpr(C1, positive=True)

        N = self.expand()
        super(Xtal, self).__init__(N.Z, N.V)
        self.args = (C0, R1, L1, C1)

    def expand(self):

        return (R(self.R1) + L(self.L1) + C(self.C1)) | C(self.C0)


class FerriteBead(Thevenin):
    """Ferrite bead (lossy inductor)

    This is modelled as a series resistor (Rs) connected
    to a parallel R, L, C network (Rp, Lp, Cp).
    """

    def __init__(self, Rs, Rp, Cp, Lp):

        self.Rs = cExpr(Rs, positive=True)
        self.Rp = cExpr(Rp, positive=True)
        self.Cp = cExpr(Cp, positive=True)
        self.Lp = cExpr(Lp, positive=True)

        N = self.expand()
        super(Xtal, self).__init__(N.Z, N.V)
        self.args = (Rs, Rp, Cp, Lp)

    def expand(self):

        return R(self.Rs) + (R(self.Rp) + L(self.Lp) + C(self.Cp))


# Import this at end to circumvent circular dependencies
from lcapy.twoport import Ladder, LSection, TSection
