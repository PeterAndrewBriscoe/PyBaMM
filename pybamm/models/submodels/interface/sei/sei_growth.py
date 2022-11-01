#
# Class for SEI growth
#
import pybamm
from .base_sei import BaseModel


class SEIGrowth(BaseModel):
    """
    Class for SEI growth.

    Parameters
    ----------
    param : parameter class
        The parameters to use for this submodel
    reaction_loc : str
        Where the reaction happens: "x-average" (SPM, SPMe, etc),
        "full electrode" (full DFN), or "interface" (half-cell model)
    options : dict
        A dictionary of options to be passed to the model.
    phase : str, optional
        Phase of the particle (default is "primary")
    cracks : bool, optional
        Whether this is a submodel for standard SEI or SEI on cracks

    **Extends:** :class:`pybamm.sei.BaseModel`
    """

    def __init__(self, param, reaction_loc, options, phase="primary", cracks=False):
        super().__init__(param, options=options, phase=phase, cracks=cracks)
        self.reaction_loc = reaction_loc

    def get_fundamental_variables(self):
        Ls = []
        for pos in ["inner", "outer"]:
            Pos = pos.capitalize()
            if self.reaction_loc == "x-average":
                L_av = pybamm.Variable(
                    f"X-averaged {pos} {self.reaction_name}thickness [m]",
                    domain="current collector",
                )
                L_av.print_name = f"L_{pos}_av"
                L = pybamm.PrimaryBroadcast(L_av, "negative electrode")
            elif self.reaction_loc == "full electrode":
                L = pybamm.Variable(
                    f"{Pos} {self.reaction_name}thickness [m]",
                    domain="negative electrode",
                    auxiliary_domains={"secondary": "current collector"},
                )
            elif self.reaction_loc == "interface":
                L = pybamm.Variable(
                    f"{Pos} {self.reaction_name}thickness [m]",
                    domain="current collector",
                )
            L.print_name = f"L_{pos}"
            Ls.append(L)

        L_inner, L_outer = Ls

        if self.options["SEI"] == "ec reaction limited":
            L_inner = 0 * L_inner  # Set L_inner to zero, copying domains

        variables = self._get_standard_thickness_variables(L_inner, L_outer)

        return variables

    def get_coupled_variables(self, variables):
        phase_param = self.phase_param
        # delta_phi = phi_s - phi_e
        T = variables["Negative electrode temperature [K]"]
        if self.reaction_loc == "interface":
            delta_phi = variables[
                "Lithium metal interface surface potential difference [V]"
            ]
            phi_s_n = variables["Lithium metal interface electrode potential [V]"]
            T = pybamm.boundary_value(T, "right")
        else:
            delta_phi = variables["Negative electrode surface potential difference [V]"]
            phi_s_n = variables["Negative electrode potential [V]"]

        # Look for current that contributes to the -IR drop
        # If we can't find the interfacial current density from the main reaction, j,
        # it's ok to fall back on the total interfacial current density, j_tot
        # This should only happen when the interface submodel is "InverseButlerVolmer"
        # in which case j = j_tot (uniform) anyway
        if "Negative electrode interfacial current density [A.m-2]" in variables:
            j = variables["Negative electrode interfacial current density [A.m-2]"]
        elif self.reaction_loc == "interface":
            j = variables["Lithium metal total interfacial current density [A.m-2]"]
        else:
            j = variables[
                "X-averaged negative electrode total "
                "interfacial current density [A.m-2]"
            ]

        L_sei_inner = variables[f"Inner {self.reaction_name}thickness [m]"]
        L_sei_outer = variables[f"Outer {self.reaction_name}thickness [m]"]
        L_sei = variables[f"Total {self.reaction_name}thickness [m]"]

        R_sei = phase_param.R_sei
        eta_SEI = delta_phi - j * L_sei * R_sei
        # Thermal prefactor for reaction, interstitial and EC models
        F_RT = param.F / (param.R * T)

        if self.options["SEI"] == "reaction limited":
            C_sei = phase_param.C_sei_reaction
            j_sei = -(1 / C_sei) * pybamm.exp(-0.5 * F_RT * eta_SEI)

        elif self.options["SEI"] == "electron-migration limited":
            U_inner = phase_param.U_inner_electron
            C_sei = phase_param.C_sei_electron
            j_sei = (phi_s_n - U_inner) / (C_sei * L_sei_inner)

        elif self.options["SEI"] == "interstitial-diffusion limited":
            C_sei = phase_param.C_sei_inter
            j_sei = -pybamm.exp(-F_RT * delta_phi) / (C_sei * L_sei_inner)

        elif self.options["SEI"] == "solvent-diffusion limited":
            C_sei = phase_param.C_sei_solvent
            j_sei = -1 / (C_sei * L_sei_outer)

        elif self.options["SEI"] == "ec reaction limited":
            C_sei_ec = phase_param.C_sei_ec
            C_ec = phase_param.C_ec

            # we have a linear system for j_sei and c_ec
            #  c_ec = 1 + j_sei * L_sei * C_ec
            #  j_sei = - C_sei_ec * c_ec * exp()
            # so
            #  j_sei = - C_sei_ec * exp() - j_sei * L_sei * C_ec * C_sei_ec * exp()
            # so
            #  j_sei = -C_sei_ec * exp() / (1 + L_sei * C_ec * C_sei_ec * exp())
            #  c_ec = 1 / (1 + L_sei * C_ec * C_sei_ec * exp())
            C_sei_exp = C_sei_ec * pybamm.exp(-0.5 * prefactor * eta_SEI)
            j_sei = -C_sei_exp / (1 + L_sei * C_ec * C_sei_exp)
            c_ec = 1 / (1 + L_sei * C_ec * C_sei_exp)

            # Get variables related to the concentration
            c_ec_av = pybamm.x_average(c_ec)

            if self.reaction == "SEI on cracks":
                name = "EC concentration on cracks"
            else:
                name = "EC surface concentration"
            variables.update(
                {f"{name} [mol.m-3]": c_ec, f"X-averaged {name} [mol.m-3]": c_ec_av}
            )

        if self.options["SEI"] == "ec reaction limited":
            inner_sei_proportion = 0
        else:
            inner_sei_proportion = phase_param.inner_sei_proportion

        # All SEI growth mechanisms assumed to have Arrhenius dependence
        Arrhenius = pybamm.exp(phase_param.E_over_RT_sei * (1 - prefactor))

        j_inner = inner_sei_proportion * Arrhenius * j_sei
        j_outer = (1 - inner_sei_proportion) * Arrhenius * j_sei

        variables.update(self._get_standard_concentration_variables(variables))
        variables.update(self._get_standard_reaction_variables(j_inner, j_outer))

        # Update whole cell variables, which also updates the "sum of" variables
        variables.update(super().get_coupled_variables(variables))

        return variables

    def set_rhs(self, variables):
        phase_name = self.phase_name
        phase_param = self.phase_param
        param = self.param

        if self.reaction_loc == "x-average":
            L_inner = variables[f"X-averaged inner {self.reaction_name}thickness [m]"]
            L_outer = variables[f"X-averaged outer {self.reaction_name}thickness [m]"]
            a_j_inner = variables[
                f"X-averaged inner {self.reaction_name}volumetric "
                "interfacial current density [A.m-3]"
            ]
            a_j_outer = variables[
                f"X-averaged outer {self.reaction_name}volumetric "
                "interfacial current density [A.m-3]"
            ]
        else:
            L_inner = variables[f"Inner {self.reaction_name}thickness [m]"]
            L_outer = variables[f"Outer {self.reaction_name}thickness [m]"]
            a_j_inner = variables[
                f"Inner {self.reaction_name}volumetric "
                "interfacial current density [A.m-3]"
            ]
            a_j_outer = variables[
                f"Outer {self.reaction_name}volumetric "
                "interfacial current density [A.m-3]"
            ]

        # The spreading term acts to spread out SEI along the cracks as they grow.
        # For SEI on initial surface (as opposed to cracks), it is zero.
        if self.reaction == "SEI on cracks":
            if self.reaction_loc == "x-average":
                l_cr = variables["X-averaged negative particle crack length [m]"]
                dl_cr = variables["X-averaged negative particle cracking rate [m.s-1]"]
            else:
                l_cr = variables["Negative particle crack length [m]"]
                dl_cr = variables["Negative particle cracking rate [m.s-1]"]
            spreading_outer = (
                dl_cr / l_cr * (self.phase_param.L_outer_crack_0 - L_outer)
            )
            spreading_inner = (
                dl_cr / l_cr * (self.phase_param.L_inner_crack_0 - L_inner)
            )
        else:
            spreading_outer = 0
            spreading_inner = 0

        Gamma_SEI = phase_param.V_bar_inner / (param.F * phase_param.z_sei)
        v_bar = phase_param.V_bar_outer / phase_param.V_bar_inner

        if self.options["SEI"] == "ec reaction limited":
            self.rhs = {L_outer: -Gamma_SEI * a_j_outer + spreading_outer}
        else:
            self.rhs = {
                L_inner: -Gamma_SEI * a_j_inner + spreading_inner,
                L_outer: -v_bar * Gamma_SEI * a_j_outer + spreading_outer,
            }

    def set_initial_conditions(self, variables):
        if self.reaction_loc == "x-average":
            L_inner = variables[f"X-averaged inner {self.reaction_name}thickness [m]"]
            L_outer = variables[f"X-averaged outer {self.reaction_name}thickness [m]"]
        else:
            L_inner = variables[f"Inner {self.reaction_name}thickness [m]"]
            L_outer = variables[f"Outer {self.reaction_name}thickness [m]"]

        if self.reaction == "SEI on cracks":
            L_inner_0 = self.phase_param.L_inner_crack_0
            L_outer_0 = self.phase_param.L_outer_crack_0
        else:
            L_inner_0 = self.phase_param.L_inner_0
            L_outer_0 = self.phase_param.L_outer_0
        if self.options["SEI"] == "ec reaction limited":
            self.initial_conditions = {L_outer: L_inner_0 + L_outer_0}
        else:
            self.initial_conditions = {L_inner: L_inner_0, L_outer: L_outer_0}
