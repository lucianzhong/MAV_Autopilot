"""
mav_dynamics
    - this file implements the dynamic equations of motion for MAV
    - use unit quaternion for the attitude state

"""
import sys
sys.path.append('..')
import numpy as np

# load message types
from messages.state_msg import StateMsg

import parameters.aerosonde_parameters as MAV
from tools.tools import Quaternion2Euler, Quaternion2Rotation

class mav_dynamics:
    def __init__(self, Ts):
        self.ts_simulation = Ts
        # set initial states based on parameter file
        # _state is the 13x1 internal state of the aircraft that is being propagated:
        # _state = [pn, pe, pd, u, v, w, e0, e1, e2, e3, p, q, r]
        self._state = np.array([MAV.pn0, MAV.pe0, MAV.pd0, MAV.u0, MAV.v0, MAV.w0,
                                MAV.e0, MAV.e1, MAV.e2, MAV.e3, MAV.p0, MAV.q0, MAV.r0])
        self._state = self._state.reshape((13, 1))

        self._wind = np.zeros((3, 1))
        self.updateVelocityData()
        #store the forces
        self._forces = np.zeros((3, 1))
        self._Va = MAV.u0
        self._alpha = 0
        self._beta = 0
        #true state
        self.msg_true_state = StateMsg()

    ###################################
    # public functions
    def update_state(self, deltas, wind):
        '''
            Integrate the differential equations defining dynamics.
            Inputs are the forces and moments on the aircraft.
            Ts is the time step between function calls.
        '''

        forces_moments = self.calcForcesAndMoments(deltas)

        # Integrate ODE using Runge-Kutta RK4 algorithm
        time_step = self.ts_simulation
        k1 = self._derivatives(self._state, forces_moments)
        k2 = self._derivatives(self._state + time_step/2.*k1, forces_moments)
        k3 = self._derivatives(self._state + time_step/2.*k2, forces_moments)
        k4 = self._derivatives(self._state + time_step*k3, forces_moments)
        self._state += time_step/6 * (k1 + 2*k2 + 2*k3 + k4)

        # normalize the quaternion
        e0 = self._state.item(6)
        e1 = self._state.item(7)
        e2 = self._state.item(8)
        e3 = self._state.item(9)
        normE = np.sqrt(e0**2+e1**2+e2**2+e3**2)
        self._state[6][0] = self._state.item(6)/normE
        self._state[7][0] = self._state.item(7)/normE
        self._state[8][0] = self._state.item(8)/normE
        self._state[9][0] = self._state.item(9)/normE

        #update velocities
        self.updateVelocityData(wind)

        # update the message class for the true state
        self._update_msg_true_state()

    ###################################
    # private functions
    def _derivatives(self, state, forces_moments):
        """
        for the dynamics xdot = f(x, u), returns f(x, u)
        """
        # extract the states
        pn = state.item(0)
        pe = state.item(1)
        pd = state.item(2)
        u = state.item(3)
        v = state.item(4)
        w = state.item(5)
        e0 = state.item(6)
        e1 = state.item(7)
        e2 = state.item(8)
        e3 = state.item(9)
        p = state.item(10)
        q = state.item(11)
        r = state.item(12)
        #   extract forces/moments
        fx = forces_moments.item(0)
        fy = forces_moments.item(1)
        fz = forces_moments.item(2)
        l = forces_moments.item(3)
        m = forces_moments.item(4)
        n = forces_moments.item(5)

        # position kinematics
        # TODO Change the line below to use Quat2Rot
        Rv_b = np.array([[e1**2 + e0**2 - e2**2 - e3**2, 2*(e1*e2 - e3*e0), 2*(e1*e3 + e2*e0)],
                         [2*(e1*e2 + e3*e0), e2**2 + e0**2 - e1**2 - e3**2, 2*(e2*e3 - e1*e0)],
                         [2*(e1*e3 - e2*e0), 2*(e2*e3 + e1*e0), e3**2 + e0**2 - e1**2 - e2**2]])

        pos_dot = Rv_b @ np.array([u, v, w]).T
        pn_dot = pos_dot.item(0)
        pe_dot = pos_dot.item(1)
        pd_dot = pos_dot.item(2)

        # position dynamics
        u_dot = r*v - q*w + 1/MAV.mass * fx
        v_dot = p*w - r*u + 1/MAV.mass * fy
        w_dot = q*u - p*v + 1/MAV.mass * fz

        # rotational kinematics
        e0_dot = (-p * e1 - q * e2 - r * e3) * 0.5
        e1_dot = (p * e0 + r * e2 - q * e3) * 0.5
        e2_dot = (q * e0 - r * e1 + p * e3) * 0.5
        e3_dot = (r * e0 + q * e1 - p * e2) * 0.5

        # rotatonal dynamics
        p_dot = MAV.gamma1 * p * q - MAV.gamma2 * q * r + MAV.gamma3 * l + MAV.gamma4 * n
        q_dot = MAV.gamma5 * p * r - MAV.gamma6 * (p**2 - r**2) + 1/MAV.Jy * m
        r_dot = MAV.gamma7 * p * q - MAV.gamma1 * q * r + MAV.gamma4 * l + MAV.gamma8 * n

        # collect the derivative of the states
        x_dot = np.array([[pn_dot, pe_dot, pd_dot, u_dot, v_dot, w_dot,
                           e0_dot, e1_dot, e2_dot, e3_dot, p_dot, q_dot, r_dot]]).T
        return x_dot

    def _update_msg_true_state(self):
        # update the true state message:
        phi, theta, psi = Quaternion2Euler(self._state[6:10])
        self.msg_true_state.pn = self._state.item(0)
        self.msg_true_state.pe = self._state.item(1)
        self.msg_true_state.h = -self._state.item(2)
        self.msg_true_state.phi = phi
        self.msg_true_state.theta = theta
        self.msg_true_state.psi = psi
        self.msg_true_state.p = self._state.item(10)
        self.msg_true_state.q = self._state.item(11)
        self.msg_true_state.r = self._state.item(12)

    def updateVelocityData(self, wind=np.zeros((6, 1))):
        debug = 1

    def calcForcesAndMoments(self, delta):
        # Calculate gravitational forces in the body frame
        fb_grav = Quaternion2Rotation(self._state[6:10]) @ np.array([[0, 0, MAV.mass * MAV.gravity]]).T

        # Calculating longitudinal forces and moments
        fx, fy, m = self.calcLongitudinalForcesAndMoments(delta.item(0))

    def calcLongitudinalForcesAndMoments(self, de):
        M = MAV.M
        alpha = self.msg_true_state.alpha
        alpha0 = MAV.alpha0
        rho = MAV.rho
        Va = self.msg_true_state.Va
        S = MAV.S_wing
        c = MAV.c
        q = self.msg_true_state.q

        #Calc lift force
        sigma_alpha = (1 + np.exp(-M * (alpha - alpha0)) + np.exp(M * (alpha + alpha0))) /..
                      ((1 + np.exp(-M * (alpha 0 alpha0))) * (1 + np.exp(M * (alpha + alpha0))))

        CL_alpha = (1 - sigma_alpha) * (MAV.C_L_0 + MAV.C_L_alpha) + ..
                   sigma_alpha * (2 * np.sign(alpha) * (np.sin(alpha)**2) * np.cos(alpha))
        F_lift = 1/2.0 * rho * (Va**2) * S * (CL_alpha + MAV.C_L_q * (c / (2 * Va)) * q + MAV.C_L_delta_e * de)