"""
This module is for canonical hrf specification.
Here we provide for SPM, Glover hrfs and finite timpulse response (FIR) models.
This module closely follows SPM implementation

Author: Bertrand Thirion, 2011--2013
"""

import warnings
import numpy as np
from scipy.stats import gamma


def _gamma_difference_hrf(tr, oversampling=16, time_length=32., onset=0.,
                         delay=6, undershoot=16., dispersion=1.,
                         u_dispersion=1., ratio=0.167):
    """ Compute an hrf as the difference of two gamma functions

    Parameters
    ----------
    tr: float, scan repeat time, in seconds
    oversampling: int, temporal oversampling factor, optional
    time_length: float, hrf kernel length, in seconds
    onset: float, onset of the hrf

    Returns
    -------
    hrf: array of shape(length / tr * oversampling, float),
         hrf sampling on the oversampled time grid
    """
    dt = tr / oversampling
    time_stamps = np.linspace(0, time_length, float(time_length) / dt)
    time_stamps -= onset / dt
    hrf = gamma.pdf(time_stamps, delay / dispersion, dt / dispersion) - \
        ratio * gamma.pdf(
        time_stamps, undershoot / u_dispersion, dt / u_dispersion)
    hrf /= hrf.sum()
    return hrf


def spm_hrf(tr, oversampling=16, time_length=32., onset=0.):
    """ Implementation of the SPM hrf model

    Parameters
    ----------
    tr: float, scan repeat time, in seconds
    oversampling: int, temporal oversampling factor, optional
    time_length: float, hrf kernel length, in seconds
    onset: float, onset of the response

    Returns
    -------
    hrf: array of shape(length / tr * oversampling, float),
         hrf sampling on the oversampled time grid
    """
    return _gamma_difference_hrf(tr, oversampling, time_length, onset)


def glover_hrf(tr, oversampling=16, time_length=32., onset=0.):
    """ Implementation of the Glover hrf model

    Parameters
    ----------
    tr: float
        scan repeat time, in seconds
    oversampling: int
        temporal oversampling factor, optional
    time_length: float
        hrf kernel length, in seconds
    onset: float
        onset of the response

    Returns
    -------
    hrf: array of shape(length / tr * oversampling, float),
         hrf sampling on the oversampled time grid
    """
    return _gamma_difference_hrf(tr, oversampling, time_length, onset,
                                delay=6, undershoot=12., dispersion=.9,
                                u_dispersion=.9, ratio=.35)


def spm_time_derivative(tr, oversampling=16, time_length=32., onset=0.):
    """Implementation of the SPM time derivative hrf (dhrf) model

    Parameters
    ----------
    tr: float
        scan repeat time, in seconds
    oversampling: int
        temporal oversampling factor, optional
    time_length: float
        hrf kernel length, in seconds
    onset: float
        onset of the response

    Returns
    -------
    dhrf: array of shape(length / tr, float),
          dhrf sampling on the provided grid
    """
    do = .1
    dhrf = 1. / do * (spm_hrf(tr, oversampling, time_length, onset + do) -
                      spm_hrf(tr, oversampling, time_length, onset))
    return dhrf


def glover_time_derivative(tr, oversampling=16, time_length=32., onset=0.):
    """Implementation of the Glover time derivative hrf (dhrf) model

    Parameters
    ----------
    tr: float
        scan repeat time, in seconds
    oversampling: int,
        temporal oversampling factor, optional
    time_length: float,
        hrf kernel length, in seconds
    onset: float,
        onset of the response

    Returns
    -------
    dhrf: array of shape(length / tr), dtype=float
          dhrf sampling on the provided grid
    """
    do = .1
    dhrf = 1. / do * (glover_hrf(tr, oversampling, time_length, onset + do) -
                      glover_hrf(tr, oversampling, time_length, onset))
    return dhrf


def spm_dispersion_derivative(tr, oversampling=16, time_length=32., onset=0.):
    """Implementation of the SPM dispersion derivative hrf model

    Parameters
    ----------
    tr: float
        scan repeat time, in seconds
    oversampling: int
        temporal oversampling factor, optional
    time_length: float
        hrf kernel length, in seconds
    onset: float
        onset of the response

    Returns
    -------
    dhrf: array of shape(length / tr * oversampling), dtype=float
          dhrf sampling on the oversampled time grid
    """
    dd = .01
    dhrf = 1. / dd * (_gamma_difference_hrf(tr, oversampling, time_length,
                                           onset, dispersion=1. + dd) -
                      spm_hrf(tr, oversampling, time_length, onset))
    return dhrf


def _sample_condition(exp_condition, frame_times, oversampling=16,
                     min_onset=-24):
    """Make a possibly oversampled event regressor from condition information.

    Parameters
    ----------
    exp_condition: 3 x n_events arraylike
        (onsets, durations, amplitudes) of events for this condition
    frame_times: array of shape(n_scans)
        time points corresponding to sampled data
    over_sampling: int, optional
        factor for oversampling event regressor
    min_onset: float, optional
        minimal onset relative to frame_times[0] (in seconds)
        events that start before frame_times[0] + min_onset are not considered

    Returns
    -------
    regressor: array of shape(over_sampling * n_scans)
        possibly oversampled event regressor
    hr_frame_times : array of shape(over_sampling * n_scans)
        time points used for regressor sampling
    """
    # Find the high-resolution frame_times
    n = frame_times.size
    min_onset = float(min_onset)
    n_hr = ((n - 1) * 1. / (frame_times.max() - frame_times.min()) *
            (frame_times.max() * (1 + 1. / (n - 1)) - frame_times.min() -
             min_onset) * oversampling) + 1

    hr_frame_times = np.linspace(frame_times.min() + min_onset,
                                frame_times.max() * (1 + 1. / (n - 1)),
                                n_hr)

    # Get the condition information
    onsets, durations, values = tuple(map(np.asanyarray, exp_condition))
    if (onsets < frame_times[0] + min_onset).any():
        warnings.warn(('Some stimulus onsets are earlier than %d in the' +
                       ' experiment and are thus not considered in the model'
                % (frame_times[0] + min_onset)), UserWarning)

    # Set up the regressor timecourse
    tmax = len(hr_frame_times)
    regressor = np.zeros_like(hr_frame_times).astype(np.float)
    t_onset = np.minimum(np.searchsorted(hr_frame_times, onsets), tmax - 1)
    regressor[t_onset] += values
    t_offset = np.minimum(np.searchsorted(hr_frame_times, onsets + durations),
                          tmax - 1)

    # Handle the case where duration is 0 by offsetting at t + 1
    for i, to in enumerate(t_offset):
        if to < (tmax - 1) and to == t_onset[i]:
            t_offset[i] += 1

    regressor[t_offset] -= values
    regressor = np.cumsum(regressor)

    return regressor, hr_frame_times


def _resample_regressor(hr_regressor, hr_frame_times, frame_times, kind='linear'):
    """ this function sub-samples the regressors at frame times

    Parameters
    ----------
    hr_regressor: array of shape(n_samples),
                  the regressor time course sampled at high temporal resolution
    hr_frame_times: array of shape(n_samples),
                   the corresponding time stamps
    frame_times: array of shape(n_scans),
                the desired time stamps
    kind: string, optional
       the kind of desired interpolation

    Returns
    -------
    regressor: array of shape(n_scans)
         the resampled regressor
    """
    from scipy.interpolate import interp1d
    f = interp1d(hr_frame_times, hr_regressor)
    return f(frame_times).T


def _orthogonalize(X):
    """ Orthogonalize every column of design `X` w.r.t preceding columns

    Parameters
    ----------
    X: array of shape(n, p)
       the data to be orthogonalized

    Returns
    -------
    X: array of shape(n, p)
       the data after orthogonalization

    Notes
    -----
    X is changed in place. the columns are not normalized
    """
    if X.size == X.shape[0]:
        return X
    from numpy.linalg import pinv
    for i in range(1, X.shape[1]):
        X[:, i] -= np.dot(X[:, i], np.dot(X[:, :i], pinv(X[:, :i])))
    return X


def _regressor_names(con_name, hrf_model, fir_delays=None):
    """ returns a list of regressor names, computed from con-name and hrf type

    Parameters
    ----------
    con_name: string
        identifier of the condition
    hrf_model: string
       identifier of the hrf model

    Returns
    -------
    names: list of strings,
        regressor names
    """
    if hrf_model == 'canonical':
        return [con_name]
    elif hrf_model == "canonical with derivative":
        return [con_name, con_name + "_derivative"]
    elif hrf_model == 'spm':
        return [con_name]
    elif hrf_model == 'spm_time':
        return [con_name, con_name + "_derivative"]
    elif hrf_model == 'spm_time_dispersion':
        return [con_name, con_name + "_derivative", con_name + "_dispersion"]
    elif hrf_model == 'fir':
        return [con_name + "_delay_%d" % i for i in fir_delays]


def _hrf_kernel(hrf_model, tr, oversampling=16, fir_delays=None):
    """ Given the specification of the hemodynamic model and time parameters,
    return the list of matching kernels

    Parameters
    ----------
    hrf_model: string
        identifier of the hrf model
    tr: float
        the repetition time in seconds
    oversampling: int
        temporal oversampling factor to have a smooth hrf
    fir_delays: list of FIR delays

    Returns
    -------
    hkernel: list of arrays
        samples of the hrf (the number depens on the hrf_model used)
    """
    if hrf_model == 'spm':
        hkernel = [spm_hrf(tr, oversampling)]
    elif hrf_model == 'spm_time':
        hkernel = [spm_hrf(tr, oversampling),
                   spm_time_derivative(tr, oversampling)]
    elif hrf_model == 'spm_time_dispersion':
        hkernel = [spm_hrf(tr, oversampling),
                   spm_time_derivative(tr, oversampling),
                   spm_dispersion_derivative(tr, oversampling)]
    elif hrf_model == 'canonical':
        hkernel = [glover_hrf(tr, oversampling)]
    elif hrf_model == 'canonical with derivative':
        hkernel = [glover_hrf(tr, oversampling),
                   glover_time_derivative(tr, oversampling)]
    elif hrf_model == 'fir':
        hkernel = [np.hstack((np.zeros(f * oversampling),
                              np.ones(oversampling)))
                   for f in fir_delays]
    else:
        raise ValueError('Unknown hrf model')
    return hkernel


def compute_regressor(exp_condition, hrf_model, frame_times, con_id='cond',
                      oversampling=16, fir_delays=None, min_onset=-24):
    """ This is the main function to convolve regressors with hrf model

    Parameters
    ----------
    exp_condition: descriptor of an experimental condition
    hrf_model: string ['spm', 'spm_time', 'spm_time_dispersion', 'canonical',
        'canonical_derivative', 'fir']
        the hrf model to be used
    frame_times: array of shape (n_scans)
        the desired sampling times
    con_id: string
        optional identifier of the condition
    oversampling: int, optional
        oversampling factor to perform the convolution
    fir_delays: array-like, dtype=int
        onsets corresponding to the fir basis
    min_onset: float, optional
        minimal onset relative to frame_times[0] (in seconds)
        events that start before frame_times[0] + min_onset are not considered

    Returns
    -------
    creg: array of shape(n_scans, n_reg)
        computed regressors sampled at frame times
    reg_names: list of strings
        corresponding regressor names

    Notes
    -----
    The different hemodynamic models can be understood as follows:
    'spm': this is the hrf model used in spm
    'spm_time': this is the spm model plus its time derivative (2 regressors)
    'spm_time_dispersion': idem, plus dispersion derivative (3 regressors)
    'canonical': this one corresponds to the Glover hrf
    'canonical_derivative': the Glover hrf + time derivative (2 regressors)
    'fir': finite impulse response basis, a set of delayed dirac models
           with arbitrary length. This one currently assumes regularly spaced
           frame times (i.e. fixed time of repetition).
    It is expected that spm standard and Glover model would not yield
    large differences in most cases.
    """
    # this is the average tr in this session, not necessarily the true tr
    tr = float(frame_times.max()) / (np.size(frame_times) - 1)

    # 1. create the high temporal resolution regressor
    hr_regressor, hr_frame_times = _sample_condition(
        exp_condition, frame_times, oversampling, min_onset)

    # 2. create the  hrf model(s)
    hkernel = _hrf_kernel(hrf_model, tr, oversampling, fir_delays)

    # 3. convolve the regressor and hrf, and downsample the regressor
    conv_reg = np.array([np.convolve(hr_regressor, h)[:hr_regressor.size]
                         for h in hkernel])

    # 4. temporally resample the regressors
    creg = _resample_regressor(conv_reg, hr_frame_times, frame_times)

    # 5. ortogonalize the regressors
    if hrf_model != 'fir':
        creg = _orthogonalize(creg)

    # 6 generate regressor names
    reg_names = _regressor_names(con_id, hrf_model, fir_delays=fir_delays)
    return creg, reg_names
