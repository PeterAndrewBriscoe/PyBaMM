#
# Equation classes for the electrolyte concentration
#
from __future__ import absolute_import, division
from __future__ import print_function, unicode_literals
import pybamm


class StefanMaxwell(pybamm.BaseModel):
    """A class that generates the expression tree for Stefan-Maxwell Diffusion in the
    electrolyte.

    Parameters
    ----------
    c_e : :class:`pybamm.Symbol`
        A symbol representing the concentration of ions in the electrolyte
    j : :class:`pybamm.Symbol`
        The interfacial current density at the electrode-electrolyte interface

    *Extends:* :class:`BaseModel`
    """

    def __init__(self, c_e, j):
        super().__init__()

        # Parameters
        sp = pybamm.standard_parameters
        spli = pybamm.standard_parameters_lithium_ion

        N_e = -sp.D_e(c_e) * (spli.epsilon ** sp.b) * pybamm.grad(c_e)

        self.rhs = {
            c_e: -pybamm.div(N_e) / spli.C_e / spli.epsilon
            + sp.s / spli.gamma_hat_e * j
        }
        self.initial_conditions = {c_e: spli.c_e_init}
        self.boundary_conditions = {
            N_e: {"left": pybamm.Scalar(0), "right": pybamm.Scalar(0)}
        }
        self.variables = {"c_e": c_e, "N_e": N_e}


class StefanMaxwellWithPorosity(pybamm.BaseModel):
    """A class that generates the expression tree for Stefan-Maxwell Diffusion in the
    electrolyte.

    Parameters
    ----------
    c_e : :class:`pybamm.Symbol`
        The electrolyte concentration
    epsilon : :class:`pybamm.Symbol`
        The (electrolyte/liquid phase) porosity
    j : :class:`pybamm.Symbol`
        An expression tree that represents the interfacial current density at the
        electrode-electrolyte interface
    param : parameter class
        The parameters to use for this submodel

    *Extends:* :class:`BaseModel`
    """

    def __init__(self, c_e, epsilon, j, param):
        super().__init__()
        sp = pybamm.standard_parameters

        # Flux
        N_e = -(epsilon ** sp.b) * pybamm.grad(c_e)
        # Porosity change
        deps_dt = -param.beta_surf * j

        # Model
        self.rhs = {
            c_e: 1
            / epsilon
            * (
                -pybamm.div(N_e) / param.C_e
                + sp.s / param.gamma_hat_e * j
                - c_e * deps_dt
            )
        }
        self.initial_conditions = {c_e: param.c_e_init}
        self.boundary_conditions = {N_e: {"left": 0, "right": 0}}
        self.variables = {"c_e": c_e, "N_e": N_e}
