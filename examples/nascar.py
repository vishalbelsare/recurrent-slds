import os
import pickle

import numpy as np
import numpy.random as npr
npr.seed(0)

import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
import matplotlib.gridspec as gridspec
from matplotlib.font_manager import FontProperties

import seaborn as sns
color_names = ["windows blue",
               "red",
               "amber",
               "faded green",
               "dusty purple",
               "crimson",
               "greyish"]
colors = sns.xkcd_palette(color_names)
sns.set_style("white")
sns.set_context("paper")

from hips.plotting.colormaps import gradient_cmap

from pybasicbayes.util.text import progprint_xrange
from pybasicbayes.models import FactorAnalysis
from pybasicbayes.distributions import \
    Regression, Gaussian, DiagonalRegression, AutoRegression

from pyhsmm.util.general import relabel_by_permutation
from autoregressive.models import ARWeakLimitStickyHDPHMM
from pyslds.util import get_empirical_ar_params

from pypolyagamma.distributions import MultinomialRegression

from pyslds.models import HMMSLDS

from rslds.decision_list import DecisionList
from rslds.models import PGRecurrentSLDS, StickyPGRecurrentSLDS, \
    PGRecurrentOnlySLDS, StickyPGRecurrentOnlySLDS
from rslds.util import compute_psi_cmoments

### Global parameters
T, K, K_true, D_obs, D_latent = 10000, 4, 4, 10, 2
mask_start, mask_stop = 0, 0
N_samples = 1000

# Save / cache the outputs
CACHE_RESULTS = False
RUN_NUMBER = 1
RESULTS_DIR = os.path.join("results", "nascar", "run{:03d}".format(RUN_NUMBER))

### Helper functions
def cached(results_name):
    if CACHE_RESULTS:
        def _cache(func):
            def func_wrapper(*args, **kwargs):
                results_file = os.path.join(RESULTS_DIR, results_name)
                if not results_file.endswith(".pkl"):
                    results_file += ".pkl"

                if os.path.exists(results_file):
                    with open(results_file, "rb") as f:
                        results = pickle.load(f)
                else:
                    results = func(*args, **kwargs)
                    with open(results_file, "wb") as f:
                        pickle.dump(results, f)

                return results
            return func_wrapper
    else:
        _cache = lambda func: func

    return _cache

### Plotting code

def make_figure(true_model, z_true, x_true, y,
                rslds, zs_rslds, x_rslds,
                z_rslds_gen, x_rslds_gen, y_rslds_gen,
                slds, zs_slds, x_slds,
                z_slds_gen, x_slds_gen, y_slds_gen):
    """
    Show the following:
     - True latent dynamics (for most likely state)
     - Segment of trajectory in latent space
     - A few examples of observations in 10D space
     - ARHMM segmentation of factors
     - rSLDS segmentation of factors
     - ARHMM synthesis
     - rSLDS synthesis
    """
    fig = plt.figure(figsize=(6.5,3.5))
    gs = gridspec.GridSpec(2,3)

    fp = FontProperties()
    fp.set_weight("bold")

    # True dynamics
    ax1 = fig.add_subplot(gs[0,0])
    plot_most_likely_dynamics(true_model.trans_distn,
                              true_model.dynamics_distns,
                              xlim=(-3,3), ylim=(-2,2),
                              ax=ax1)

    # Overlay a partial trajectory
    plot_trajectory(z_true[1:1000], x_true[1:1000], ax=ax1, ls="-")
    ax1.set_title("True Latent Dynamics")
    plt.figtext(.025, 1-.075, '(a)', fontproperties=fp)

    # Plot a few output dimensions
    ax2 = fig.add_subplot(gs[1, 0])
    for n in range(D_obs):
        plot_data(z_true[1:1000], y[1:1000, n], ax=ax2, ls="-")
    ax2.set_xlabel("Time")
    ax2.set_ylabel("$y$")
    ax2.set_title("Observed Data")
    plt.figtext(.025, .5 - .075, '(b)', fontproperties=fp)

    # Plot the inferred dynamics under the rSLDS
    ax3 = fig.add_subplot(gs[0, 1])
    plot_most_likely_dynamics(rslds.trans_distn,
                              rslds.dynamics_distns,
                              xlim=(-3, 3), ylim=(-2, 2),
                              ax=ax3)

    # Overlay a partial trajectory
    plot_trajectory(zs_rslds[-1][1:1000], x_rslds[1:1000], ax=ax3, ls="-")
    ax3.set_title("Inferred Dynamics (rSLDS)")
    plt.figtext(.33 + .025, 1. - .075, '(c)', fontproperties=fp)

    # Plot something... z samples?
    ax4 = fig.add_subplot(gs[1,1])
    plot_z_samples(zs_rslds, zref=z_true, plt_slice=(0,1000), ax=ax4)
    ax4.set_title("Discrete State Samples")
    plt.figtext(.33 + .025, .5 - .075, '(d)', fontproperties=fp)

    # Plot simulated SLDS data
    ax5 = fig.add_subplot(gs[0, 2])
    # for n, ls in enumerate(["-", ":", "-."]):
    #     plot_data(z_slds_gen[-1000:], y_slds_gen[-1000:, n], ax=ax5, ls=ls)
    plot_trajectory(z_slds_gen[-1000:], x_slds_gen[-1000:], ax=ax5, ls="-")
    # ax5.set_xlabel("Time")
    # ax5.set_ylabel("$y$")
    plt.grid(True)
    ax5.set_title("Generated States (SLDS)")
    plt.figtext(.66 + .025, 1. - .075, '(e)', fontproperties=fp)

    # Plot simulated rSLDS data
    ax6 = fig.add_subplot(gs[1, 2])
    # for n, ls in enumerate(["-", ":", "-."]):
    #     plot_data(z_rslds_gen[-1000:], y_rslds_gen[-1000:, n], ax=ax6, ls=ls)
    # ax6.set_xlabel("Time")
    # ax6.set_ylabel("$y$")
    plot_trajectory(z_rslds_gen[-1000:], x_rslds_gen[-1000:], ax=ax6, ls="-")
    ax6.set_title("Generated States (rSLDS)")
    plt.grid(True)
    plt.figtext(.66 + .025, .5 - .075, '(f)', fontproperties=fp)



    plt.tight_layout()
    # plt.savefig(os.path.join(results_dir, "nascar.png"), dpi=200)
    # plt.savefig(os.path.join(results_dir, "nascar.pdf"))
    plt.show()


def plot_dynamics(A, b=None, ax=None, plot_center=True,
                  xlim=(-4,4), ylim=(-3,3), npts=20,
                  color='r'):
    b = np.zeros((A.shape[0], 1)) if b is None else b
    x = np.linspace(*xlim, npts)
    y = np.linspace(*ylim, npts)
    X,Y = np.meshgrid(x,y)
    xy = np.column_stack((X.ravel(), Y.ravel()))

    # dydt_m = xy.dot(A.T) + b.T - xy
    dydt_m = xy.dot(A.T) + b.T - xy

    if ax is None:
        fig = plt.figure(figsize=(6,6))
        ax = fig.add_subplot(111)

    ax.quiver(xy[:, 0], xy[:, 1],
              dydt_m[:, 0], dydt_m[:, 1],
              color=color, alpha=1.0,
              headwidth=5.)

    # Plot the stable point
    if plot_center:
        try:
            center = -np.linalg.solve(A-np.eye(D_latent), b)
            ax.plot(center[0], center[1], 'o', color=color, markersize=8)
        except:
            print("Dynamics are not invertible!")

    ax.set_xlabel('$x_1$', fontsize=12, labelpad=10)
    ax.set_ylabel('$x_2$', fontsize=12, labelpad=10)

    return ax

def plot_all_dynamics(dynamics_distns,
                      filename=None):

    fig = plt.figure(figsize=(12,3))
    for k in range(K):
        ax = fig.add_subplot(1,K,k+1)
        plot_dynamics(dynamics_distns[k].A[:,:D_latent],
                      b=dynamics_distns[k].A[:,D_latent:],
                      plot_center=False,
                      color=colors[k], ax=ax)

    if filename is not None:
        fig.savefig(os.path.join(RESULTS_DIR, filename))


def plot_most_likely_dynamics(
        reg, dynamics_distns,
        xlim=(-4, 4), ylim=(-3, 3),  nxpts=20, nypts=10,
        alpha=0.8,
        ax=None, figsize=(3,3)):

    x = np.linspace(*xlim, nxpts)
    y = np.linspace(*ylim, nypts)
    X, Y = np.meshgrid(x, y)
    xy = np.column_stack((X.ravel(), Y.ravel()))

    # Get the probability of each state at each xy location
    inputs = np.hstack((np.zeros((nxpts * nypts, reg.D_in - 2)), xy))
    prs = reg.pi(inputs)
    z = np.argmax(prs, axis=1)


    if ax is None:
        fig = plt.figure(figsize=figsize)
        ax = fig.add_subplot(111)

    for k in range(K):
        A = dynamics_distns[k].A[:, :D_latent]
        b = dynamics_distns[k].A[:, D_latent:]
        dydt_m = xy.dot(A.T) + b.T - xy

        zk = z == k
        if zk.sum(0) > 0:
            ax.quiver(xy[zk, 0], xy[zk, 1],
                      dydt_m[zk, 0], dydt_m[zk, 1],
                      color=colors[k], alpha=alpha)

    ax.set_xlabel('$x_1$')
    ax.set_ylabel('$x_2$')

    plt.tight_layout()

    return ax

def plot_trans_probs(reg,
                     xlim=(-4,4), ylim=(-3,3), n_pts=50,
                     ax=None,
                     filename=None):
    XX,YY = np.meshgrid(np.linspace(*xlim,n_pts),
                        np.linspace(*ylim,n_pts))
    XY = np.column_stack((np.ravel(XX), np.ravel(YY)))

    D_reg = reg.D_in
    inputs = np.hstack((np.zeros((n_pts**2, D_reg-2)), XY))
    test_prs = reg.pi(inputs)

    if ax is None:
        fig = plt.figure(figsize=(10,6))
        ax = fig.add_subplot(111)

    for k in range(K):
        start = np.array([1., 1., 1., 0.])
        end = np.concatenate((colors[k], [0.5]))
        cmap = gradient_cmap([start, end])
        im1 = ax.imshow(test_prs[:,k].reshape(*XX.shape),
                         extent=xlim + tuple(reversed(ylim)),
                         vmin=0, vmax=1, cmap=cmap)

        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        # ax.set_title("State {}".format(k+1))

    plt.tight_layout()
    return ax

def plot_trajectory(zhat, x, ax=None, ls="-", filename=None):
    zcps = np.concatenate(([0], np.where(np.diff(zhat))[0] + 1, [zhat.size]))
    if ax is None:
        fig = plt.figure(figsize=(4, 4))
        ax = fig.gca()
    for start, stop in zip(zcps[:-1], zcps[1:]):
        ax.plot(x[start:stop + 1, 0],
                x[start:stop + 1, 1],
                lw=1, ls=ls,
                color=colors[zhat[start]],
                alpha=1.0)

    # ax.set_xlabel('$x_1$', fontsize=12, labelpad=10)
    # ax.set_ylabel('$x_2$', fontsize=12, labelpad=10)
    if filename is not None:
        plt.savefig(filename)

    return ax

def plot_trajectory_and_probs(z, x,
                              ax=None,
                              trans_distn=None,
                              title=None,
                              filename=None,
                              **trargs):
    if ax is None:
        fig = plt.figure(figsize=(10, 6))
        ax = fig.add_subplot(111)

    if trans_distn is not None:
        xlim = abs(x[:, 0]).max()
        xlim = (-xlim, xlim)
        ylim = abs(x[:, 0]).max()
        ylim = (-ylim, ylim)
        ax = plot_trans_probs(trans_distn, ax=ax,
                              xlim=xlim, ylim=ylim)
    plot_trajectory(z, x, ax=ax, **trargs)
    plt.tight_layout()
    plt.title(title)
    if filename is not None:
        plt.savefig(os.path.join(RESULTS_DIR, filename))

    return ax


def plot_data(zhat, y, ax=None, ls="-", filename=None):
    zcps = np.concatenate(([0], np.where(np.diff(zhat))[0] + 1, [zhat.size]))
    if ax is None:
        fig = plt.figure(figsize=(4, 4))
        ax = fig.gca()
    for start, stop in zip(zcps[:-1], zcps[1:]):
        stop = min(y.shape[0], stop+1)
        ax.plot(np.arange(start, stop),
                y[start:stop ],
                lw=1, ls=ls,
                color=colors[zhat[start]],
                alpha=1.0)

    # ax.set_xlabel('$x_1$', fontsize=12, labelpad=10)
    # ax.set_ylabel('$x_2$', fontsize=12, labelpad=10)
    if filename is not None:
        plt.savefig(filename)

    return ax

def plot_separate_trans_probs(reg,
                              xlim=(-4,4), ylim=(-3,3), n_pts=100,
                              ax=None,
                              filename=None):
    XX,YY = np.meshgrid(np.linspace(*xlim,n_pts),
                        np.linspace(*ylim,n_pts))
    XY = np.column_stack((np.ravel(XX), np.ravel(YY)))

    D_reg = reg.D_in
    inputs = np.hstack((np.zeros((n_pts**2, D_reg-2)), XY))
    test_prs = reg.pi(inputs)

    if ax is None:
        fig = plt.figure(figsize=(12,3))

    for k in range(K):
        ax = fig.add_subplot(1,K,k+1)
        cmap = gradient_cmap([np.ones(3), colors[k]])
        im1 = ax.imshow(test_prs[:,k].reshape(*XX.shape),
                         extent=xlim + tuple(reversed(ylim)),
                         vmin=0, vmax=1, cmap=cmap)

        ax.set_xlim(xlim)
        ax.set_ylim(ylim)

        divider = make_axes_locatable(ax)
        cax = divider.append_axes("right", size="5%", pad=0.05)
        plt.colorbar(im1, cax=cax, ax=ax)
        # ax.set_title("State {}".format(k+1))

    plt.tight_layout()
    return ax


def plot_z_samples(zs, zref=None,
                   plt_slice=None,
                   N_iters=None,
                   title=None,
                   ax=None,
                   filename=None):

    if ax is None:
        fig = plt.figure(figsize=(10,5))
        ax = fig.add_subplot(111)

    zs = np.array(zs)
    if plt_slice is None:
        plt_slice = (0, zs.shape[1])
    if N_iters is None:
        N_iters = zs.shape[0]

    im = ax.imshow(zs[:,slice(*plt_slice)], aspect='auto', vmin=0, vmax=K-1,
                     cmap=gradient_cmap(colors[:K]), interpolation="nearest",
                     extent=plt_slice + (N_iters, 0))
    # ax.autoscale(False)
    ax.set_xticks([])
    # ax.set_yticks([0, N_iters])
    ax.set_ylabel("Iteration")

    if zref is not None:
        divider = make_axes_locatable(ax)
        ax2 = divider.append_axes("bottom", size="10%", pad=0.05)

        zref = np.atleast_2d(zref)
        im = ax2.imshow(zref[:, slice(*plt_slice)], aspect='auto', vmin=0, vmax=K-1,
                         cmap=gradient_cmap(colors[:K]), interpolation="nearest")
        # ax2.autoscale(False)
        ax.set_xticks([])
        ax2.set_yticks([])
        ax2.set_ylabel("True $z$", rotation=0)
        ax2.yaxis.set_label_coords(-.15, -.5)
        ax2.set_xlabel("Time")

    if title is not None:
        ax.set_title(title)

    if filename is not None:
        plt.savefig(os.path.join(RESULTS_DIR, filename))

### Make an example with 2D latent states and 4 discrete states
@cached("simulated_data")
def simulate_nascar():
    assert K_true == 4
    def random_rotation(n, theta):
        rot = np.array([[np.cos(theta), -np.sin(theta)],
                        [np.sin(theta), np.cos(theta)]])
        out = np.zeros((n,n))
        out[:2,:2] = rot
        q = np.linalg.qr(np.random.randn(n,n))[0]
        # q = np.eye(n)
        return q.dot(out).dot(q.T)

    As = [random_rotation(D_latent, np.pi/24.),
          random_rotation(D_latent, np.pi/48.)]

    # Set the center points for each system
    centers = [np.array([+2.0, 0.]),
               np.array([-2.0, 0.])]
    bs = [-(A - np.eye(D_latent)).dot(center) for A, center in zip(As, centers)]

    # Add a "right" state
    As.append(np.eye(D_latent))
    bs.append(np.array([+0.1, 0.]))

    # Add a "right" state
    As.append(np.eye(D_latent))
    bs.append(np.array([-0.25, 0.]))

    # Construct multinomial regression to divvy up the space #
    w1, b1 = np.array([+1.0, 0.0]), np.array([-2.0])   # x + b > 0 -> x > -b
    w2, b2 = np.array([-1.0, 0.0]), np.array([-2.0])   # -x + b > 0 -> x < b
    w3, b3 = np.array([0.0, +1.0]), np.array([0.0])    # y > 0

    reg_W = np.row_stack((w1, w2, w3))
    reg_b = np.row_stack((b1, b2, b3))

    # Scale the weights to make the transition boundary sharper
    reg_scale = 100.
    reg_b *= reg_scale
    reg_W *= reg_scale

    # Account for stick breaking asymmetry
    mu_b, _ = compute_psi_cmoments(np.ones(K_true))
    reg_b += mu_b[:,None]

    # Make a recurrent SLDS with these params #
    dynamics_distns = [
        Regression(
            A=np.column_stack((A,b)),
            sigma=1e-4 * np.eye(D_latent),
            nu_0=D_latent + 2,
            S_0=1e-4 * np.eye(D_latent),
            M_0=np.zeros((D_latent, D_latent + 1)),
            K_0=np.eye(D_latent + 1),
        )
        for A,b in zip(As, bs)]

    init_dynamics_distns = [
        Gaussian(
            mu=np.array([0.0, 1.0]),
            sigma=1e-3 * np.eye(D_latent))
        for _ in range(K)]

    C = np.hstack((npr.randn(D_obs, D_latent), np.zeros((D_obs, 1))))
    emission_distns = \
        DiagonalRegression(D_obs, D_latent+1,
                           A=C, sigmasq=1e-5 *np.ones(D_obs),
                           alpha_0=2.0, beta_0=2.0)

    model = PGRecurrentSLDS(
        trans_params=dict(A=np.hstack((np.zeros((K_true-1, K_true)), reg_W)), b=reg_b,
                          sigmasq_A=100., sigmasq_b=100.),
        init_state_distn='uniform',
        init_dynamics_distns=init_dynamics_distns,
        dynamics_distns=dynamics_distns,
        emission_distns=emission_distns,
        alpha=3.)

    #########################
    # Sample from the model #
    #########################
    inputs = np.ones((T, 1))
    y, x, z = model.generate(T=T, inputs=inputs)

    # Maks off some data
    mask = np.ones((T,D_obs), dtype=bool)
    mask[mask_start:mask_stop] = False

    # Print the true parameters
    np.set_printoptions(precision=2)
    print("True W_markov:\n{}".format(model.trans_distn.A[:,:K_true]))
    print("True W_input:\n{}".format(model.trans_distn.A[:,K_true:]))

    return model, inputs, z, x, y, mask

### Factor Analysis and PCA for dimensionality reduction
# @cached("factor_analysis")
def fit_factor_analysis(y, mask=None, N_iters=100):
    print("Fitting Factor Analysis")
    model = FactorAnalysis(D_obs, D_latent)

    if mask is None:
        mask = np.ones_like(y, dtype=bool)

    # Center the data
    b = y.mean(0)
    data = model.add_data(y-b, mask=mask)
    for _ in progprint_xrange(N_iters):
        model.resample_model()

    C_init = np.column_stack((model.W, b))
    return data.Z, C_init

# @cached("pca")
def fit_pca(y, whiten=True):
    print("Fitting PCA")
    from sklearn.decomposition import PCA
    model = PCA(n_components=D_latent, whiten=whiten)
    x_init = model.fit_transform(y)
    C_init = model.components_.T
    b_init = model.mean_[:,None]
    sigma = np.sqrt(model.explained_variance_)

    # inverse transform is given by
    # X.dot(sigma * C_init.T) + b_init.T
    if whiten:
        C_init = sigma * C_init

    return x_init, np.column_stack((C_init, b_init))

### Make an ARHMM for initialization
# @cached("arhmm")
def fit_arhmm(x, affine=True):
    print("Fitting Sticky ARHMM")
    dynamics_hypparams = \
        dict(nu_0=D_latent + 2,
             S_0=np.eye(D_latent),
             M_0=np.hstack((np.eye(D_latent), np.zeros((D_latent, int(affine))))),
             K_0=np.eye(D_latent + affine),
             affine=affine)
    dynamics_hypparams = get_empirical_ar_params([x], dynamics_hypparams)

    dynamics_distns = [
        AutoRegression(
            A=np.column_stack((0.99 * np.eye(D_latent),
                               np.zeros((D_latent, int(affine))))),
            sigma=np.eye(D_latent),
            **dynamics_hypparams)
        for _ in range(K)]

    init_distn = Gaussian(nu_0=D_latent + 2,
                          sigma_0=np.eye(D_latent),
                          mu_0=np.zeros(D_latent),
                          kappa_0=1.0)

    arhmm = ARWeakLimitStickyHDPHMM(
        init_state_distn='uniform',
        init_emission_distn=init_distn,
        obs_distns=dynamics_distns,
        alpha=3.0, kappa=10.0, gamma=3.0)

    arhmm.add_data(x)

    lps = []
    for _ in progprint_xrange(1000):
        arhmm.resample_model()
        lps.append(arhmm.log_likelihood())

    z_init = arhmm.states_list[0].stateseq
    z_init = np.concatenate(([0], z_init))

    return arhmm, z_init

### Use a DecisionList to permute the discrete states
def fit_decision_list(z, y):
    print("Fitting Decision List")
    dlist = DecisionList(K, D_latent)
    dlist.fit(y[:-1], z[1:])

    dl_reg = MultinomialRegression(1, K, D_latent)
    dl_reg.A = dlist.weights.copy()
    dl_reg.b = dlist.biases[:,None].copy()

    z_perm = \
        relabel_by_permutation(z, np.argsort(dlist.permutation))

    return z_perm, dl_reg

def make_rslds_parameters(C_init):
    init_dynamics_distns = [
        Gaussian(
            mu=np.zeros(D_latent),
            sigma=np.eye(D_latent),
            nu_0=D_latent + 2, sigma_0=3. * np.eye(D_latent),
            mu_0=np.zeros(D_latent), kappa_0=1.0,
        )
        for _ in range(K)]

    dynamics_distns = [
        Regression(
            nu_0=D_latent + 2,
            S_0=1e-4 * np.eye(D_latent),
            M_0=np.hstack((np.eye(D_latent), np.zeros((D_latent, 1)))),
            K_0=np.eye(D_latent + 1),
        )
        for _ in range(K)]

    emission_distns = \
        DiagonalRegression(D_obs, D_latent + 1,
                           A=C_init.copy(), sigmasq=np.ones(D_obs),
                           alpha_0=2.0, beta_0=2.0)

    return init_dynamics_distns, dynamics_distns, emission_distns


# @cached("slds")
def fit_slds(inputs, z_init, x_init, y, mask, C_init,
              N_iters=10000):
    print("Fitting standard SLDS")
    init_dynamics_distns, dynamics_distns, emission_distns = \
        make_rslds_parameters(C_init)

    slds = HMMSLDS(
        init_state_distn='uniform',
        init_dynamics_distns=init_dynamics_distns,
        dynamics_distns=dynamics_distns,
        emission_distns=emission_distns,
        alpha=3.)

    slds.add_data(y, inputs=inputs, mask=mask)

    # Initialize states
    slds.states_list[0].stateseq = z_init.copy().astype(np.int32)
    slds.states_list[0].gaussian_states = x_init.copy()

    # Initialize dynamics
    print("Initializing dynamics with Gibbs sampling")
    for _ in progprint_xrange(100):
        slds.resample_dynamics_distns()

    # Fit the model
    lps = []
    z_smpls = []
    for _ in progprint_xrange(N_iters):
        slds.resample_model()
        lps.append(slds.log_likelihood())
        z_smpls.append(slds.stateseqs[0].copy())

    x_test = slds.states_list[0].gaussian_states
    z_smpls = np.array(z_smpls)
    lps = np.array(lps)

    return slds, lps, z_smpls, x_test

# @cached("rslds")
def fit_rslds(inputs, z_init, x_init, y, mask, dl_reg, C_init,
              N_iters=10000):
    print("Fitting rSLDS")
    init_dynamics_distns, dynamics_distns, emission_distns = \
        make_rslds_parameters(C_init)

    rslds = PGRecurrentSLDS(
        trans_params=dict(sigmasq_A=10000., sigmasq_b=10000.,
                          A=np.hstack((np.zeros((K - 1, K)), dl_reg.A)),
                          b=dl_reg.b),
        init_state_distn='uniform',
        init_dynamics_distns=init_dynamics_distns,
        dynamics_distns=dynamics_distns,
        emission_distns=emission_distns,
        fixed_emission=False,
        alpha=3.)

    rslds.add_data(y, inputs=inputs, mask=mask)

    # Initialize states
    rslds.states_list[0].stateseq = z_init.copy()
    rslds.states_list[0].gaussian_states = x_init.copy()

    # Initialize dynamics
    print("Initializing dynamics with Gibbs sampling")
    for _ in progprint_xrange(100):
        rslds.resample_dynamics_distns()

    # Fit the model
    lps = []
    z_smpls = []
    for _ in progprint_xrange(N_iters):
        rslds.resample_model()
        lps.append(rslds.log_likelihood())
        z_smpls.append(rslds.stateseqs[0].copy())

    x_test = rslds.states_list[0].gaussian_states
    z_smpls = np.array(z_smpls)
    lps = np.array(lps)

    print("Inf W_markov:\n{}".format(rslds.trans_distn.A[:, :K]))
    print("Inf W_input:\n{}".format(rslds.trans_distn.A[:, K:]))

    return rslds, lps, z_smpls, x_test


# @cached("sticky_rslds")
def fit_sticky_rslds(inputs, z_init, x_init, y, mask, dl_reg, C_init,
                     N_iters=10000):
    print("Fitting Sticky rSLDS")
    init_dynamics_distns, dynamics_distns, emission_distns = \
        make_rslds_parameters(C_init)

    rslds = StickyPGRecurrentSLDS(
        D_in=D_latent,
        trans_params=dict(sigmasq_A=10000., sigmasq_b=10000., kappa=100.,
                          A=np.hstack((np.zeros((K - 1, K)), dl_reg.A)),
                          b=dl_reg.b),
        init_state_distn='uniform',
        init_dynamics_distns=init_dynamics_distns,
        dynamics_distns=dynamics_distns,
        emission_distns=emission_distns,
        fixed_emission=False,
        alpha=3.)

    rslds.add_data(y, inputs=inputs, mask=mask)

    # Initialize states
    rslds.states_list[0].stateseq = z_init.copy()
    rslds.states_list[0].gaussian_states = x_init.copy()

    # Initialize dynamics
    print("Initializing dynamics with Gibbs sampling")
    for _ in progprint_xrange(100):
        rslds.resample_dynamics_distns()

    # Fit the model
    lps = []
    z_smpls = []
    for _ in progprint_xrange(N_iters):
        rslds.resample_model()
        lps.append(rslds.log_likelihood())
        z_smpls.append(rslds.stateseqs[0].copy())

    x_test = rslds.states_list[0].gaussian_states
    z_smpls = np.array(z_smpls)
    lps = np.array(lps)

    print("Inf W_markov:\n{}".format(rslds.trans_distn.A[:, :K]))
    print("Inf W_input:\n{}".format(rslds.trans_distn.A[:, K:]))

    return rslds, lps, z_smpls, x_test

# @cached("roslds")
def fit_roslds(inputs, z_init, x_init, y, mask, dl_reg, C_init,
               N_iters=10000):
    print("Fitting input only rSLDS")
    init_dynamics_distns, dynamics_distns, emission_distns = \
        make_rslds_parameters(C_init)

    rslds = PGRecurrentOnlySLDS(
        trans_params=dict(sigmasq_A=10000., sigmasq_b=10000.,
                          A=np.hstack((np.zeros((K-1, K)), dl_reg.A)),
                          b=dl_reg.b),
        init_state_distn='uniform',
        init_dynamics_distns=init_dynamics_distns,
        dynamics_distns=dynamics_distns,
        emission_distns=emission_distns,
        fixed_emission=False,
        alpha=3.)

    rslds.add_data(y, inputs=inputs, mask=mask)

    # Initialize states
    rslds.states_list[0].stateseq = z_init.copy()
    rslds.states_list[0].gaussian_states = x_init.copy()

    # Initialize dynamics
    print("Initializing dynamics with Gibbs sampling")
    for _ in progprint_xrange(100):
        rslds.resample_dynamics_distns()

    # Fit the model
    lps = []
    z_smpls = []
    for _ in progprint_xrange(N_iters):
        rslds.resample_model()
        lps.append(rslds.log_likelihood())
        z_smpls.append(rslds.stateseqs[0].copy())

    x_test = rslds.states_list[0].gaussian_states
    z_smpls = np.array(z_smpls)
    lps = np.array(lps)

    print("Inf W_markov:\n{}".format(rslds.trans_distn.A[:,:K]))
    print("Inf W_input:\n{}".format(rslds.trans_distn.A[:,K:]))
    return rslds, lps, z_smpls, x_test


# @cached("sticky_roslds")
def fit_sticky_roslds(inputs, z_init, x_init, y, mask, dl_reg, C_init,
                      N_iters=10000):
    print("Fitting sticky input only rSLDS")
    init_dynamics_distns, dynamics_distns, emission_distns = \
        make_rslds_parameters(C_init)

    rslds = StickyPGRecurrentOnlySLDS(
        trans_params=dict(sigmasq_A=10000., sigmasq_b=10000.,
                          kappa=1., sigmasq_kappa=1.0,
                          A=np.hstack((np.zeros((K-1, K)), dl_reg.A)),
                          b=dl_reg.b),
        init_state_distn='uniform',
        init_dynamics_distns=init_dynamics_distns,
        dynamics_distns=dynamics_distns,
        emission_distns=emission_distns,
        fixed_emission=False,
        alpha=3.)

    rslds.add_data(y, inputs=inputs, mask=mask)

    # Initialize states
    rslds.states_list[0].stateseq = z_init.copy()
    rslds.states_list[0].gaussian_states = x_init.copy()

    # Initialize dynamics
    print("Initializing dynamics with Gibbs sampling")
    for _ in progprint_xrange(100):
        rslds.resample_dynamics_distns()

    # Fit the model
    lps = []
    z_smpls = []
    for _ in progprint_xrange(N_iters):
        rslds.resample_model()
        lps.append(rslds.log_likelihood())
        z_smpls.append(rslds.stateseqs[0].copy())

    x_test = rslds.states_list[0].gaussian_states
    z_smpls = np.array(z_smpls)
    lps = np.array(lps)

    print("Inf W_markov:\n{}".format(rslds.trans_distn.A[:,:K]))
    print("Inf W_input:\n{}".format(rslds.trans_distn.A[:,K:]))
    return rslds, lps, z_smpls, x_test


if __name__ == "__main__":
    ## Simulate NASCAR data
    true_model, inputs, z_true, x_true, y, mask = simulate_nascar()

    # plot_most_likely_dynamics(true_model.trans_distn,
    #                           true_model.dynamics_distns,
    #                           figsize=(3,1.5))
    #
    # plot_all_dynamics(true_model.dynamics_distns,
    #                   filename="true_dynamics.png")

    ## Run PCA to get 2D dynamics
    # x_init, C_init = fit_factor_analysis(y, mask=mask)
    x_init, C_init = fit_pca(y)

    ## Fit an ARHMM for initialization
    #  Basically, we're only fitting on data that was observed
    good_inds = np.all(mask, axis=1)
    good_x_init = x_init[good_inds]
    arhmm, good_z_init = fit_arhmm(good_x_init)
    z_init = np.random.randint(0,K,size=T)
    z_init[good_inds] = good_z_init
    z_init[mask_start:mask_stop] = z_init[mask_start-1]
    # Zero out missing data
    x_init[~good_inds] = 0

    # plot_trajectory_and_probs(
    #     z_init[1:], x_init[1:],
    #     title="Sticky ARHMM",
    #     filename="sticky_arhmm.png")
    #
    # plot_all_dynamics(arhmm.obs_distns,
    #                   filename="sticky_arhmm_dynamics.png")

    ## Fit a DecisionList to get a permutation of z_init
    z_perm, dl_reg = fit_decision_list(z_init, x_init)

    ## Fit a standard SLDS
    slds, slds_lps, slds_z_smpls, slds_x = \
        fit_slds(inputs, z_perm, x_init, y, mask, C_init, N_iters=N_samples)

    ## Fit a recurrent SLDS
    # rslds, rslds_lps, rslds_z_smpls, rslds_x = \
    #     fit_rslds(inputs, z_perm, x_init, y, mask, dl_reg, C_init, N_iters=N_iters)
    #
    # plot_trajectory_and_probs(
    #     rslds_z_smpls[-1][1:], rslds_x[1:],
    #     trans_distn=rslds.trans_distn,
    #     title="Recurrent SLDS",
    #     filename="rslds.png")
    #
    # plot_all_dynamics(rslds.dynamics_distns,
    #                   filename="rslds_dynamics.png")
    #
    # plot_z_samples(rslds_z_smpls,
    #                plt_slice=(0,1000),
    #                filename="rslds_zsamples.png")

    ## Fit an input-only recurrent SLDS
    roslds, roslds_lps, roslds_z_smpls, roslds_x = \
        fit_roslds(inputs, z_perm, x_init, y, mask, dl_reg, C_init, N_iters=N_samples)

    plot_trajectory_and_probs(
        roslds_z_smpls[-1][1:], roslds_x[1:],
        trans_distn=roslds.trans_distn,
        title="Recurrent SLDS")

    ## Generate from the model
    T_gen = 2000
    inputs = np.ones((T_gen, 1))
    roslds_y_gen, roslds_x_gen, roslds_z_gen = roslds.generate(T=T_gen, inputs=inputs)
    slds_y_gen, slds_x_gen, slds_z_gen = slds.generate(T=T_gen, inputs=inputs)

    make_figure(true_model, z_true, x_true, y,
                roslds, roslds_z_smpls, roslds_x,
                roslds_z_gen, roslds_x_gen, roslds_y_gen,
                slds, slds_z_smpls, slds_x,
                slds_z_gen, slds_x_gen, slds_y_gen,
                )

    plt.show()
