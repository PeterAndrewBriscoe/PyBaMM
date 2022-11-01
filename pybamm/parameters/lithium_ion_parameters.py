#
# Standard parameters for lithium-ion battery models
#
import pybamm
from .base_parameters import BaseParameters, NullParameters


class LithiumIonParameters(BaseParameters):
    """
    Standard parameters for lithium-ion battery models

    Layout:
        1. Dimensional Parameters
        2. Dimensional Functions
        3. Scalings
        4. Dimensionless Parameters
        5. Dimensionless Functions
        6. Input Current

    Parameters
    ----------

    options : dict, optional
        A dictionary of options to be passed to the parameters. The options that
        can be set are listed below.

            * "particle shape" : str, optional
                Sets the model shape of the electrode particles. This is used to
                calculate the surface area to volume ratio. Can be "spherical"
                (default). TODO: implement "cylindrical" and "platelet".
            * "working electrode": str
                Which electrode(s) intercalates and which is counter. If "both"
                (default), the model is a standard battery. Otherwise can be "negative"
                or "positive" to indicate a half-cell model.

    """

    def __init__(self, options=None):
        self.options = options

        # Get geometric, electrical and thermal parameters
        self.geo = pybamm.GeometricParameters(options)
        self.elec = pybamm.electrical_parameters
        self.therm = pybamm.thermal_parameters

        # Initialize domain parameters
        self.n = DomainLithiumIonParameters("negative", self)
        self.s = DomainLithiumIonParameters("separator", self)
        self.p = DomainLithiumIonParameters("positive", self)
        self.domain_params = {
            "negative": self.n,
            "separator": self.s,
            "positive": self.p,
        }

        # Set parameters and scales
        self._set_dimensional_parameters()
        # self._set_scales()
        # self._set_dimensionless_parameters()

        # Set input current
        # self._set_input_current()

    def _set_dimensional_parameters(self):
        """Defines the dimensional parameters"""
        # Physical constants
        self.R = pybamm.constants.R
        self.F = pybamm.constants.F
        self.k_b = pybamm.constants.k_b
        self.q_e = pybamm.constants.q_e

        # Thermal parameters
        self.T_ref = self.therm.T_ref
        self.T_init = self.therm.T_init
        self.T_amb = self.therm.T_amb
        # self.T_init = self.therm.T_init

        # Macroscale geometry
        self.L_x = self.geo.L_x
        self.L = self.geo.L
        self.L_y = self.geo.L_y
        self.L_z = self.geo.L_z
        self.r_inner = self.geo.r_inner
        self.r_outer = self.geo.r_outer
        self.A_cc = self.geo.A_cc
        self.A_cooling = self.geo.A_cooling
        self.V_cell = self.geo.V_cell

        # Electrical
        self.current_with_time = self.elec.current_with_time
        self.current_density_with_time = self.elec.current_density_with_time
        self.Q = self.elec.Q
        self.n_electrodes_parallel = self.elec.n_electrodes_parallel
        self.n_cells = self.elec.n_cells
        self.voltage_low_cut = self.elec.voltage_low_cut
        self.voltage_high_cut = self.elec.voltage_high_cut

        # Domain parameters
        for domain in self.domain_params.values():
            domain._set_dimensional_parameters()

        # Electrolyte properties
        self.c_e_typ = pybamm.Parameter("Typical electrolyte concentration [mol.m-3]")

        self.epsilon_init = pybamm.concatenation(
            *[
                self.domain_params[domain.split()[0]].epsilon_init
                for domain in self.options.whole_cell_domains
            ]
        )

        # Lithium plating parameters
        self.V_bar_plated_Li = pybamm.Parameter(
            "Lithium metal partial molar volume [m3.mol-1]"
        )
        self.c_Li_typ = pybamm.Parameter(
            "Typical plated lithium concentration [mol.m-3]"
        )
        self.c_plated_Li_0 = pybamm.Parameter(
            "Initial plated lithium concentration [mol.m-3]"
        )

        # Initial conditions
        # Note: the initial concentration in the electrodes can be set as a function
        # of through-cell position, so is defined later as a function
        self.c_e_init = pybamm.Parameter(
            "Initial concentration in electrolyte [mol.m-3]"
        )

        self.alpha_T_cell = pybamm.Parameter(
            "Cell thermal expansion coefficient [m.K-1]"
        )

        # Total lithium
        # Electrolyte
        c_e_av_init = pybamm.xyz_average(self.epsilon_init) * self.c_e_typ
        self.n_Li_e_init = c_e_av_init * self.L_x * self.A_cc

        self.n_Li_particles_init = self.n.n_Li_init + self.p.n_Li_init
        self.n_Li_init = self.n_Li_particles_init + self.n_Li_e_init

        # Reference OCP based on initial concentration
        self.ocv_init = self.p.prim.U_init - self.n.prim.U_init

    def chi(self, c_e, T):
        """
        Thermodynamic factor:
            (1-2*t_plus) is for Nernst-Planck,
            2*(1-t_plus) for Stefan-Maxwell,
        see Bizeray et al (2016) "Resolving a discrepancy ...".
        """
        return (2 * (1 - self.t_plus(c_e, T))) * (self.one_plus_dlnf_dlnc(c_e, T))

    def chiRT_over_Fc(self, c_e, T):
        """
        chi * (1 + Theta * T) / c,
        as it appears in the electrolyte potential equation
        """
        tol = pybamm.settings.tolerances["chi__c_e"]
        c_e = pybamm.maximum(c_e, tol)
        return (self.R * T / self.F) * self.chi(c_e, T) / c_e

    def t_plus(self, c_e, T):
        """Cation transference number (dimensionless)"""
        inputs = {"Electrolyte concentration [mol.m-3]": c_e, "Temperature [K]": T}
        return pybamm.FunctionParameter("Cation transference number", inputs)

    def one_plus_dlnf_dlnc(self, c_e, T):
        """Thermodynamic factor (dimensionless)"""
        inputs = {"Electrolyte concentration [mol.m-3]": c_e, "Temperature [K]": T}
        return pybamm.FunctionParameter("1 + dlnf/dlnc", inputs)

    def D_e(self, c_e, T):
        """Dimensional diffusivity in electrolyte"""
        tol = pybamm.settings.tolerances["D_e__c_e"]
        c_e = pybamm.maximum(c_e, tol)
        inputs = {"Electrolyte concentration [mol.m-3]": c_e, "Temperature [K]": T}
        return pybamm.FunctionParameter("Electrolyte diffusivity [m2.s-1]", inputs)

    def kappa_e(self, c_e, T):
        """Dimensional electrolyte conductivity"""
        tol = pybamm.settings.tolerances["D_e__c_e"]
        c_e = pybamm.maximum(c_e, tol)
        inputs = {"Electrolyte concentration [mol.m-3]": c_e, "Temperature [K]": T}
        return pybamm.FunctionParameter("Electrolyte conductivity [S.m-1]", inputs)

    def j0_stripping(self, c_e, c_Li, T):
        """Dimensional exchange-current density for stripping [A.m-2]"""
        inputs = {
            "Electrolyte concentration [mol.m-3]": c_e,
            "Plated lithium concentration [mol.m-3]": c_Li,
            "Temperature [K]": T,
        }
        return pybamm.FunctionParameter(
            "Exchange-current density for stripping [A.m-2]", inputs
        )

    def j0_plating(self, c_e, c_Li, T):
        """Dimensional exchange-current density for plating [A.m-2]"""
        inputs = {
            "Electrolyte concentration [mol.m-3]": c_e,
            "Plated lithium concentration [mol.m-3]": c_Li,
            "Temperature [K]": T,
        }
        return pybamm.FunctionParameter(
            "Exchange-current density for plating [A.m-2]", inputs
        )

    def dead_lithium_decay_rate(self, L_sei):
        """Dimensional dead lithium decay rate [s-1]"""
        inputs = {"Total SEI thickness [m]": L_sei}
        return pybamm.FunctionParameter("Dead lithium decay rate [s-1]", inputs)


class DomainLithiumIonParameters(BaseParameters):
    def __init__(self, domain, main_param):
        self.domain = domain
        self.main_param = main_param

        self.geo = getattr(main_param.geo, domain[0])
        self.therm = getattr(main_param.therm, domain[0])

        if domain != "separator":
            self.prim = ParticleLithiumIonParameters("primary", self)
            phases_option = int(getattr(main_param.options, domain)["particle phases"])
            if phases_option >= 2:
                self.sec = ParticleLithiumIonParameters("secondary", self)
            else:
                self.sec = NullParameters()
        else:
            self.prim = NullParameters()
            self.sec = NullParameters()

        self.phase_params = {"primary": self.prim, "secondary": self.sec}

    def _set_dimensional_parameters(self):
        main = self.main_param
        domain, Domain = self.domain_Domain

        if domain == "separator":
            x = pybamm.standard_spatial_vars.x_s * main.L_x
            self.epsilon_init = pybamm.FunctionParameter(
                "Separator porosity", {"Through-cell distance (x) [m]": x}
            )
            self.epsilon_inactive = 1 - self.epsilon_init
            self.b_e = self.geo.b_e
            self.L = self.geo.L
            return

        x = (
            pybamm.SpatialVariable(
                f"x_{domain[0]}",
                domain=[f"{domain} electrode"],
                auxiliary_domains={"secondary": "current collector"},
                coord_sys="cartesian",
            )
            * main.L_x
        )

        # Macroscale geometry
        self.L_cc = self.geo.L_cc
        self.L = self.geo.L

        for phase in self.phase_params.values():
            phase._set_dimensional_parameters()

        # Tab geometry (for pouch cells)
        self.L_tab = self.geo.L_tab
        self.Centre_y_tab = self.geo.Centre_y_tab
        self.Centre_z_tab = self.geo.Centre_z_tab
        self.A_tab = self.geo.A_tab

        # Particle properties
        self.sigma_cc = pybamm.Parameter(
            f"{Domain} current collector conductivity [S.m-1]"
        )
        if main.options.electrode_types[domain] == "porous":
            self.epsilon_init = pybamm.FunctionParameter(
                f"{Domain} electrode porosity", {"Through-cell distance (x) [m]": x}
            )
            epsilon_s_tot = sum(phase.epsilon_s for phase in self.phase_params.values())
            self.epsilon_inactive = 1 - self.epsilon_init - epsilon_s_tot

            self.cap_init = sum(phase.cap_init for phase in self.phase_params.values())
            # Use primary phase to set the reference potential
            # self.U_ref = self.prim.U(self.prim.c_init_av, main.T_ref)
        # else:
        #     self.U_ref = pybamm.Scalar(0)

        self.n_Li_init = sum(phase.n_Li_init for phase in self.phase_params.values())

        # Tortuosity parameters
        self.b_e = self.geo.b_e
        self.b_s = self.geo.b_s

        self.C_dl = pybamm.Parameter(
            f"{Domain} electrode double-layer capacity [F.m-2]"
        )

        # Mechanical parameters
        self.nu = pybamm.Parameter(f"{Domain} electrode Poisson's ratio")
        self.E = pybamm.Parameter(f"{Domain} electrode Young's modulus [Pa]")
        self.c_0 = pybamm.Parameter(
            f"{Domain} electrode reference concentration for free of deformation "
            "[mol.m-3]"
        )
        self.Omega = pybamm.Parameter(
            f"{Domain} electrode partial molar volume [m3.mol-1]"
        )
        self.l_cr_0 = pybamm.Parameter(f"{Domain} electrode initial crack length [m]")
        self.w_cr = pybamm.Parameter(f"{Domain} electrode initial crack width [m]")
        self.rho_cr = pybamm.Parameter(
            f"{Domain} electrode number of cracks per unit area [m-2]"
        )
        self.b_cr = pybamm.Parameter(f"{Domain} electrode Paris' law constant b")
        self.m_cr = pybamm.Parameter(f"{Domain} electrode Paris' law constant m")
        self.Eac_cr = pybamm.Parameter(
            f"{Domain} electrode activation energy for cracking rate [kJ.mol-1]"
        )
        # intermediate variables  [K*m^3/mol]
        self.theta = (self.Omega / main.R) * 2 * self.Omega * self.E / 9 / (1 - self.nu)

        # Loss of active material parameters
        self.m_LAM = pybamm.Parameter(
            f"{Domain} electrode LAM constant exponential term"
        )
        self.beta_LAM = pybamm.Parameter(
            f"{Domain} electrode LAM constant proportional term [s-1]"
        )
        self.stress_critical = pybamm.Parameter(
            f"{Domain} electrode critical stress [Pa]"
        )
        self.beta_LAM_sei = pybamm.Parameter(
            f"{Domain} electrode reaction-driven LAM factor [m3.mol-1]"
        )

        # utilisation parameters
        self.u_init = pybamm.Parameter(
            f"Initial {domain} electrode interface utilisation"
        )
        self.beta_utilisation = pybamm.Parameter(
            f"{Domain} electrode current-driven interface utilisation factor [m3.mol-1]"
        )

    def sigma(self, T):
        """Dimensional electrical conductivity in electrode"""
        inputs = {"Temperature [K]": T}
        Domain = self.domain.capitalize()
        return pybamm.FunctionParameter(
            f"{Domain} electrode conductivity [S.m-1]", inputs
        )


class ParticleLithiumIonParameters(BaseParameters):
    def __init__(self, phase, domain_param):
        self.domain_param = domain_param
        self.domain = domain_param.domain
        self.main_param = domain_param.main_param
        self.phase = phase
        self.set_phase_name()
        if self.phase == "primary":
            self.geo = domain_param.geo.prim
        elif self.phase == "secondary":
            self.geo = domain_param.geo.sec

    def _set_dimensional_parameters(self):
        main = self.main_param
        domain, Domain = self.domain_Domain
        phase_name = self.phase_name
        pref = self.phase_prefactor

        # Electrochemical reactions
        self.ne = pybamm.Parameter(f"{pref}{Domain} electrode electrons in reaction")

        # Intercalation kinetics
        self.mhc_lambda = pybamm.Parameter(
            f"{pref}{Domain} electrode reorganization energy [eV]"
        )
        self.alpha_bv = pybamm.Parameter(
            f"{pref}{Domain} electrode Butler-Volmer transfer coefficient"
        )

        if self.domain == "negative":
            # SEI parameters
            self.V_bar_inner = pybamm.Parameter(
                f"{pref}Inner SEI partial molar volume [m3.mol-1]"
            )
            self.V_bar_outer = pybamm.Parameter(
                f"{pref}Outer SEI partial molar volume [m3.mol-1]"
            )

            self.m_sei = pybamm.Parameter(
                f"{pref}SEI reaction exchange current density [A.m-2]"
            )

            self.R_sei = pybamm.Parameter(f"{pref}SEI resistivity [Ohm.m]")
            self.D_sol = pybamm.Parameter(
                f"{pref}Outer SEI solvent diffusivity [m2.s-1]"
            )
            self.c_sol = pybamm.Parameter(f"{pref}Bulk solvent concentration [mol.m-3]")
            self.U_inner = pybamm.Parameter(
                f"{pref}Inner SEI open-circuit potential [V]"
            )
            self.U_outer = pybamm.Parameter(
                f"{pref}Outer SEI open-circuit potential [V]"
            )
            self.kappa_inner = pybamm.Parameter(
                f"{pref}Inner SEI electron conductivity [S.m-1]"
            )
            self.D_li = pybamm.Parameter(
                f"{pref}Inner SEI lithium interstitial diffusivity [m2.s-1]"
            )
            self.c_li_0 = pybamm.Parameter(
                f"{pref}Lithium interstitial reference concentration [mol.m-3]"
            )
            self.L_inner_0_dim = pybamm.Parameter(
                f"{pref}Initial inner SEI thickness [m]"
            )
            self.L_outer_0_dim = pybamm.Parameter(
                f"{pref}Initial outer SEI thickness [m]"
            )
            self.L_sei_0_dim = self.L_inner_0_dim + self.L_outer_0_dim
            self.E_sei = pybamm.Parameter(
                f"{pref}SEI growth activation energy [J.mol-1]"
            )

            # EC reaction
            self.c_ec_0_dim = pybamm.Parameter(
                f"{pref}EC initial concentration in electrolyte [mol.m-3]"
            )
            self.D_ec_dim = pybamm.Parameter(f"{pref}EC diffusivity [m2.s-1]")
            self.k_sei_dim = pybamm.Parameter(
                f"{pref}SEI kinetic rate constant [m.s-1]"
            )
            self.U_sei_dim = pybamm.Parameter(f"{pref}SEI open-circuit potential [V]")

        if main.options.electrode_types[domain] == "planar":
            self.n_Li_init = pybamm.Scalar(0)
            self.U_init_dim = pybamm.Scalar(0)
            return

        x = (
            pybamm.SpatialVariable(
                f"x_{domain[0]}",
                domain=[f"{domain} electrode"],
                auxiliary_domains={"secondary": "current collector"},
                coord_sys="cartesian",
            )
            * main.L_x
        )
        r = (
            pybamm.SpatialVariable(
                f"r_{domain[0]}",
                domain=[f"{domain} {self.phase_name}particle"],
                auxiliary_domains={
                    "secondary": f"{domain} electrode",
                    "tertiary": "current collector",
                },
                coord_sys="spherical polar",
            )
            * self.geo.R_typ
        )

        # Macroscale geometry
        # Note: the surface area to volume ratio is defined later with the function
        # parameters. The particle size as a function of through-cell position is
        # already defined in geometric_parameters.py
        self.R = self.geo.R
        self.R_typ = self.geo.R_typ

        # Particle properties
        self.c_max = pybamm.Parameter(
            f"{pref}Maximum concentration in {domain} electrode [mol.m-3]"
        )

        # Particle-size distribution parameters
        self.R_min = self.geo.R_min
        self.R_max = self.geo.R_max
        self.sd_a = self.geo.sd_a
        self.f_a_dist = self.geo.f_a_dist

        self.epsilon_s = pybamm.FunctionParameter(
            f"{pref}{Domain} electrode active material volume fraction",
            {"Through-cell distance (x) [m]": x},
        )
        self.c_init = pybamm.FunctionParameter(
            f"{pref}Initial concentration in {domain} electrode [mol.m-3]",
            {
                "Radial distance (r) [m]": r,
                "Through-cell distance (x) [m]": pybamm.PrimaryBroadcast(
                    x, f"{domain} {phase_name}particle"
                ),
            },
        )
        self.c_init_av = pybamm.xyz_average(pybamm.r_average(self.c_init))
        self.sto_init_av = self.c_init_av / self.c_max
        eps_c_init_av = pybamm.xyz_average(
            self.epsilon_s * pybamm.r_average(self.c_init)
        )
        self.n_Li_init = eps_c_init_av * self.domain_param.L * main.A_cc

        eps_s_av = pybamm.xyz_average(self.epsilon_s)
        self.elec_loading = eps_s_av * self.domain_param.L * self.c_max * main.F / 3600
        self.cap_init = self.elec_loading * main.A_cc

        self.U_init = self.U(self.sto_init_av, main.T_init)

    def D(self, sto, T):
        """Dimensional diffusivity in particle. Note this is defined as a
        function of stochiometry"""
        Domain = self.domain.capitalize()
        inputs = {
            f"{self.phase_prefactor}{Domain} particle stoichiometry": sto,
            "Temperature [K]": T,
        }
        return pybamm.FunctionParameter(
            f"{self.phase_prefactor}{Domain} electrode diffusivity [m2.s-1]",
            inputs,
        )

    def j0(self, c_e, c_s_surf, T):
        """Dimensional exchange-current density [A.m-2]"""
        domain, Domain = self.domain_Domain
        inputs = {
            "Electrolyte concentration [mol.m-3]": c_e,
            f"{Domain} particle surface concentration [mol.m-3]": c_s_surf,
            f"{self.phase_prefactor}Maximum {domain} particle "
            "surface concentration [mol.m-3]": self.c_max,
            "Temperature [K]": T,
            f"{self.phase_prefactor}Maximum {domain} particle "
            "surface concentration [mol.m-3]": self.c_max,
        }
        return pybamm.FunctionParameter(
            f"{self.phase_prefactor}{Domain} electrode "
            "exchange-current density [A.m-2]",
            inputs,
        )

    def U(self, sto, T, lithiation=None):
        """Dimensional open-circuit potential [V]"""
        # bound stoichiometry between tol and 1-tol. Adding 1/sto + 1/(sto-1) later
        # will ensure that ocp goes to +- infinity if sto goes into that region
        # anyway
        Domain = self.domain.capitalize()
        tol = pybamm.settings.tolerances["U__c_s"]
        sto = pybamm.maximum(pybamm.minimum(sto, 1 - tol), tol)
        if lithiation is None:
            lithiation = ""
        else:
            lithiation = lithiation + " "
        inputs = {f"{self.phase_prefactor}{Domain} particle stoichiometry": sto}
        u_ref = pybamm.FunctionParameter(
            f"{self.phase_prefactor}{Domain} electrode {lithiation}OCP [V]", inputs
        )
        # add a term to ensure that the OCP goes to infinity at 0 and -infinity at 1
        # this will not affect the OCP for most values of sto
        # see #1435
        u_ref = u_ref + 1e-6 * (1 / sto + 1 / (sto - 1))
        dudt_dim_func = self.dUdT(sto)
        d = self.domain[0]
        dudt_dim_func.print_name = r"\frac{dU_{" + d + r"}}{dT}"
        return u_ref + (T - self.main_param.T_ref) * dudt_dim_func

    def dUdT(self, sto):
        """
        Dimensional entropic change of the open-circuit potential [V.K-1]
        """
        domain, Domain = self.domain_Domain
        inputs = {
            f"{Domain} particle stoichiometry": sto,
            f"{self.phase_prefactor}Maximum {domain} particle "
            "surface concentration [mol.m-3]": self.c_max,
        }
        return pybamm.FunctionParameter(
            f"{self.phase_prefactor}{Domain} electrode OCP entropic change [V.K-1]",
            inputs,
        )
