"""Provide mutual information estimators for the Estimator_mi class.

This module exports methods for mutual information (MI) estimation
in the Estimator_mi class.
"""
from pkg_resources import resource_filename
import numpy as np
import math
from scipy.special import digamma
from . import neighbour_search_opencl as nsocl
from . import idtxl_exceptions as ex
from . import idtxl_utils as utils

try:
    import jpype as jp
except ImportError as err:
    ex.package_missing(err, 'Jpype is not available on this system. Install it'
                            ' from https://pypi.python.org/pypi/JPype1 to use '
                            'JAVA/JIDT-powered CMI estimation.')


def is_parallel(estimator_name):
    """Check if estimator can estimate CMI for multiple chunks in parallel."""
    parallel_estimators = {'opencl_kraskov': True,
                           'jidt_kraskov': False,
                           'jidt_discrete': False,
                           'jidt_gaussian': False}
    try:
        return parallel_estimators[estimator_name]
    except KeyError:
        print('Unknown estimator name, assuming estimator to be serial.')
        return False


def opencl_kraskov(self, var1, var2, n_chunks=1, opts=None):
    """Calculate mutual information using an opencl Kraskov implementation.

    Calculate the mutual information between two variables using an
    opencl-based Kraskov type 1 estimator. Multiple MIs can be estimated in
    parallel, where each instance is called a 'chunk'. References:

    Kraskov, A., Stoegbauer, H., & Grassberger, P. (2004). Estimating mutual
    information. Physical review E, 69(6), 066138.

    This function is ment to be imported into the set_estimator module and used
    as a method in the Estimator_mi class.

    Args:
        self : instance of Estimator_mi
            function is supposed to be used as part of the Estimator_mi class
        var1 : numpy array
            realisations of the first random variable, where dimensions are
            realisations x variable dimension
        var2 : numpy array
            realisations of the second random variable
        n_chunks : int [optional]
            number of data sets or chunks (default=1)
        opts : dict [optional]
            sets estimation parameters:

            - 'kraskov_k' - no. nearest neighbours for KNN search (default=4)
            - 'theiler_t' - no. next temporal neighbours ignored in KNN and
              range searches (default='ACT', the autocorr. time of the target)
            - 'noise_level' - random noise added to the data (default=1e-8)
            - 'gpuid' - ID of the GPU device to be used (default=0)

    Returns:
        float
            conditional mutual information

    Note:
        The Theiler window ignores trial boundaries. The MI estimator does add
        noise to the data as a default. To make analysis runs replicable set
        noise_level to 0.
    """
    if opts is None:
        opts = {}
    elif type(opts) is not dict:
        raise TypeError('Opts should be a dictionary.')

    # Get defaults for estimator options
    kraskov_k = int(opts.get('kraskov_k', 4))
    theiler_t = int(opts.get('theiler_t', 0))  # TODO necessary?
    noise_level = np.float32(opts.get('noise_level', 1e-8))
    gpuid = int(opts.get('gpuid', 0))
    nchunkspergpu = n_chunks

    # Add random noise.
    var1 += np.random.normal(scale=noise_level, size=var1.shape)
    var2 += np.random.normal(scale=noise_level, size=var2.shape)

    # build pointsets - Note we assume that pointsets are given in IDTxl conv.
    # also cast to single precision as required by opencl neighbour search
    # 1. full space
    pointset_full_space = np.hstack((var1, var2))
    pointset_full_space = pointset_full_space.astype('float32')
    n_dim_full = pointset_full_space.shape[1]
    var1 = var1.astype('float32')
    n_dim_var1 = var1.shape[1]
    var2 = var2.astype('float32')
    n_dim_var2 = var2.shape[1]

    signallengthpergpu = pointset_full_space.shape[0]
#    print("working with signallength: %i" %signallengthpergpu)
    chunksize = signallengthpergpu / nchunkspergpu  # TODO check for integer result

    # KNN search in highest dimensional space.
    indexes, distances = nsocl.knn_search(pointset_full_space, n_dim_full,
                                          kraskov_k, theiler_t, nchunkspergpu,
                                          gpuid)
    radii = distances[distances.shape[0] - 1, :]

    # Get neighbour counts in the ranges defined by the k-th nearest
    # neighbour in the KNN search.
    count_var1 = nsocl.range_search(var1, n_dim_var1, radii, theiler_t,
                                    nchunkspergpu, gpuid)
    count_var2 = nsocl.range_search(var2, n_dim_var2, radii, theiler_t,
                                    nchunkspergpu, gpuid)

    # Return the results, one mi per chunk of data.
    mi_array = -np.inf * np.ones(nchunkspergpu).astype('float64')
    for chunknum in range(0, nchunkspergpu):
        mi = (digamma(kraskov_k) + digamma(chunksize) -
              np.mean(digamma(count_var1[chunknum * chunksize:(chunknum + 1) *
                                         chunksize] + 1) +
              digamma(count_var2[chunknum * chunksize:(chunknum + 1) *
                                 chunksize] + 1)))
        mi_array[chunknum] = mi
    return mi_array


def jidt_kraskov(self, var1, var2, opts=None):
    """Calculate mutual information with JIDT's Kraskov implementation.

    Calculate the mutual information between two variables. Call JIDT via jpype
    and use the Kraskov 1 estimator. References:

    Kraskov, A., Stoegbauer, H., & Grassberger, P. (2004). Estimating mutual
    information. Physical review E, 69(6), 066138.

    Lizier, Joseph T. (2014). JIDT: an information-theoretic toolkit for
    studying the dynamics of complex systems. Front. Robot. AI, 1(11).

    This function is ment to be imported into the set_estimator module and used
    as a method in the Estimator_mi class.

    Args:
        self : instance of Estimator_mi
            function is supposed to be used as part of the Estimator_mi class
        var1 : numpy array
            realisations of the first random variable, where dimensions are
            realisations x variable dimension
        var2 : numpy array
            realisations of the second random variable
        opts : dict [optional]
            sets estimation parameters:

            - 'kraskov_k' - no. nearest neighbours for KNN search (default=4)
            - 'normalise' - z-standardise data (default=False)
            - 'theiler_t' - no. next temporal neighbours ignored in KNN and
              range searches (default='ACT', the autocorr. time of the target)
            - 'noise_level' - random noise added to the data (default=1e-8)
            - 'local_values' - return local TE instead of average TE
              (default=False)
            - 'num_threads' - no. CPU threads used for estimation
              (default='USE_ALL', this uses all available cores on the
              machine!)

    Returns:
        float
            mutual information

    Note:
        Some technical details: JIDT normalises over realisations, IDTxl
        normalises over raw data once, outside the MI calculator to save
        computation time. The Theiler window ignores trial boundaries. The
        MI estimator does add noise to the data as a default. To make analysis
        runs replicable set noise_level to 0.
    """
    if opts is None:
        opts = {}
    elif type(opts) is not dict:
        raise TypeError('Opts should be a dictionary.')

    # Get defaults for estimator options
    kraskov_k = str(opts.get('kraskov_k', 4))
    normalise = str(opts.get('normalise', False)).lower()
    theiler_t = str(opts.get('theiler_t', 0))  # TODO necessary?
    noise_level = str(opts.get('noise_level', 1e-8))
    local_values = opts.get('local_values', False)
    num_threads = str(opts.get('num_threads', 'USE_ALL'))
    lag = opts.get('lag', 0)

    # Shift second variable to account for a lag if requested
    if lag > 0:
        var1 = var1[:-lag]
        var2 = var2[lag:]

    jarLocation = resource_filename(__name__, 'infodynamics.jar')
    if not jp.isJVMStarted():
        jp.startJVM(jp.getDefaultJVMPath(), '-ea', ('-Djava.class.path=' +
                    jarLocation))
    calcClass = (jp.JPackage('infodynamics.measures.continuous.kraskov').
                 MutualInfoCalculatorMultiVariateKraskov1)
    calc = calcClass()
    calc.setProperty('NORMALISE', normalise)
    calc.setProperty('k', kraskov_k)
    calc.setProperty('NOISE_LEVEL_TO_ADD', noise_level)
    calc.setProperty('DYN_CORR_EXCL', theiler_t)
    calc.setProperty('NUM_THREADS', num_threads)
    calc.initialise(var1.shape[1], var2.shape[1])
    calc.setObservations(var1, var2)
    if local_values:
        return np.array(calc.computeLocalOfPreviousObservations())
    else:
        return calc.computeAverageLocalOfObservations()


def jidt_discrete(self, var1, var2, opts=None):
    """Calculate mutual information with JIDT's discrete-variable implementation.

    Calculate the mutual information between two variables. Call JIDT via jpype
    and use the discrete estimator.

    References:

    Lizier, Joseph T. (2014). JIDT: an information-theoretic toolkit for
    studying the dynamics of complex systems. Front. Robot. AI, 1(11).

    This function is meant to be imported into the set_estimator module and used
    as a method in the Estimator_mi class.

    Args:
        self : instance of Estimator_mi
            function is supposed to be used as part of the Estimator_mi class
        var1 : numpy array (either of integers or doubles to be discretised)
            realisations of the first random variable.
            Can be multidimensional (i.e. multivariate) where dimensions of the
            array are realisations x variable dimension
        var2 : numpy array (either of integers or doubles to be discretised)
            realisations of the second random variable.
            Can be multidimensional (i.e. multivariate) where dimensions of the
            array are realisations x variable dimension
        opts : dict [optional]
            sets estimation parameters:
            - 'num_discrete_bins' - number of discrete bins/levels or the base
                                    of each dimension of the discrete variables
                                    (default=2 for binary)
            - 'lag' - time difference across which to take MI from variable 1
                      to variable 2, i.e. lag from variable 1 to 2 (default=0)
            - 'discretise_method' - if and how to discretise incoming
                                    continuous variables to discrete values,
                                    can be
                                    'max_ent' maximum entropy binning
                                    'equal' equal size bins
                                    'none' no binning (default='none')
            - 'debug' - set debug prints from the calculator on

    Returns:
        float
            mutual information

    """
    # Parse parameters:
    if opts is None:
        opts = {}

    num_discrete_bins = int(opts.get('num_discrete_bins', 2))
    lag = int(opts.get('lag', 0))
    discretise_method = opts.get('discretise_method', 'none')
    debug = opts.get('debug', False)

    # Work out the number of samples and dimensions for each variable, before
    #  we collapse all dimensions down:
    if len(var1.shape) > 1:
        # var1 is is multidimensional
        var1_dimensions = var1.shape[1]
    else:
        # var1 is unidimensional
        var1_dimensions = 1
    if len(var2.shape) > 1:
        # var2 is is multidimensional
        var2_dimensions = var2.shape[1]
    else:
        # var2 is unidimensional
        var2_dimensions = 1
    # Work out the base we need to use, after combining across all dimensions:
    max_base = int(math.pow(num_discrete_bins, max(var1_dimensions, var2_dimensions)))

    # Now discretise if required
    if (discretise_method == 'equal'):
        var1 = utils.discretise(var1, num_discrete_bins)
        var2 = utils.discretise(var2, num_discrete_bins)
    elif (discretise_method == 'max_ent'):
        var1 = utils.discretise_max_ent(var1, num_discrete_bins)
        var2 = utils.discretise_max_ent(var2, num_discrete_bins)
    elif (discretise_method == 'none'):  # check if data is really discretised
        assert issubclass(var1.dtype.type, np.integer), ('No discretisation '
               'requested, but input 1 is not an integer numpy array.')
        assert issubclass(var2.dtype.type, np.integer), ('No discretisation '
               'requested, but input 2 is not an integer numpy array.')
        assert min(var1) >= 0, 'Minimum of input 1 is smaller than 0.'
        assert min(var2) >= 0, 'Minimum of input 1 is smaller than 0.'
        assert max(var1) < num_discrete_bins, (
                'Maximum of input 1 is larger than the no. discrete bins - 1.')
        assert max(var2) < num_discrete_bins, (
                'Maximum of input 2 is larger than the no. discrete bins - 1.')

    # Then collapse any mulitvariates into univariate arrays:
    var1 = utils.combine_discrete_dimensions(var1, num_discrete_bins)
    var2 = utils.combine_discrete_dimensions(var2, num_discrete_bins)

    # And finally make the MI calculation:
    jarLocation = resource_filename(__name__, 'infodynamics.jar')
    if not jp.isJVMStarted():
        jp.startJVM(jp.getDefaultJVMPath(), '-ea', ('-Djava.class.path=' +
                    jarLocation))
    calcClass = (jp.JPackage('infodynamics.measures.discrete').
                 MutualInformationCalculatorDiscrete)
    calc = calcClass(max_base, lag)
    calc.setDebug(debug)
    calc.initialise()
    # Unfortunately no faster way to pass numpy arrays in than this list conversion
    calc.addObservations(jp.JArray(jp.JInt, 1)(var1.tolist()),
                         jp.JArray(jp.JInt, 1)(var2.tolist()))
    return calc.computeAverageLocalOfObservations()


def jidt_gaussian(self, var1, var2, opts=None):
    """Calculate mutual information with JIDT's Gaussian implementation.

    Calculate the mutual information between two variables. Call JIDT via jpype
    and use the Gaussian estimator. References:

    Lizier, Joseph T. (2014). JIDT: an information-theoretic toolkit for
    studying the dynamics of complex systems. Front. Robot. AI, 1(11).

    This function is ment to be imported into the set_estimator module and used
    as a method in the Estimator_mi class.

    Args:
        self : instance of Estimator_mi
            function is supposed to be used as part of the Estimator_mi class
        var1 : numpy array
            realisations of the first random variable, where dimensions are
            realisations x variable dimension
        var2 : numpy array
            realisations of the second random variable
        opts : dict [optional]
            sets estimation parameters:

            - 'local_values' - return local TE instead of average TE
              (default=False)

    Returns:
        float
            mutual information

    Note:
        Some technical details: JIDT normalises over realisations, IDTxl
        normalises over raw data once, outside the MI calculator to save
        computation time. The Theiler window ignores trial boundaries. The
        MI estimator does add noise to the data as a default. To make analysis
        runs replicable set noise_level to 0.
    """
    if opts is None:
        opts = {}
    elif type(opts) is not dict:
        raise TypeError('Opts should be a dictionary.')

    # Get defaults for estimator options
    local_values = opts.get('local_values', False)

    jarLocation = resource_filename(__name__, 'infodynamics.jar')
    if not jp.isJVMStarted():
        jp.startJVM(jp.getDefaultJVMPath(), '-ea', ('-Djava.class.path=' +
                    jarLocation))
    calcClass = (jp.JPackage('infodynamics.measures.continuous.gaussian').
                 MutualInfoCalculatorMultiVariateGaussian)
    calc = calcClass()
    calc.initialise(var1.shape[1], var2.shape[1])
    calc.setObservations(var1, var2)
    if local_values:
        return np.array(calc.computeLocalOfPreviousObservations())
    else:
        return calc.computeAverageLocalOfObservations()
