"""Test AIS analysis class.

This module provides unit tests for the AIS analysis class.
"""
import pytest
import random as rn
import numpy as np
from idtxl.data import Data
from idtxl.active_information_storage import Active_information_storage
from test_estimators_cmi import jpype_missing, opencl_missing


@jpype_missing
def test_active_information_storage_init():
    """Test instance creation for Active_information_storage class."""
    # Test error on missing estimator
    with pytest.raises(KeyError):
        Active_information_storage(max_lag=5, options={})

    # Test tau larger than maximum lag
    analysis_opts = {'cmi_calc_name': 'jidt_kraskov'}
    with pytest.raises(RuntimeError):
        Active_information_storage(max_lag=5, options=analysis_opts, tau=10)
    # Test negative tau and maximum lag
    with pytest.raises(RuntimeError):
        Active_information_storage(max_lag=5, options=analysis_opts, tau=-10)
    with pytest.raises(RuntimeError):
        Active_information_storage(max_lag=-5, options=analysis_opts, tau=1)

    # Invalid: process is not an int
    dat = Data()
    dat.generate_mute_data(10, 3)
    ais = Active_information_storage(max_lag=5,
                                     tau=1,
                                     options=analysis_opts)
    with pytest.raises(RuntimeError):  # no int
        ais.analyse_single_process(data=dat, process=1.5)
    with pytest.raises(RuntimeError):  # negative
        ais.analyse_single_process(data=dat, process=-1)
    with pytest.raises(RuntimeError):  # not in data
        ais.analyse_single_process(data=dat, process=10)
    with pytest.raises(RuntimeError):  # wrong type
        ais.analyse_single_process(data=dat, process={})

    # Force conditionals
    analysis_opts['add_conditionals'] = [(0, 1), (1, 3)]
    ais = Active_information_storage(max_lag=5,
                                     tau=1,
                                     options=analysis_opts)


def test_analyse_network():
    """Test AIS estimation for the whole network."""
    dat = Data()
    dat.generate_mute_data(10, 3)
    ais = Active_information_storage(max_lag=5,
                                     tau=1,
                                     options={'cmi_calc_name': 'jidt_kraskov'})
    # Test analysis of 'all' processes
    r = ais.analyse_network(data=dat)
    k = list(r.keys())
    assert all(np.array(k) == np.arange(dat.n_processes)), (
                'Network analysis did not run on all targets.')
    # Test check for correct definition of processes
    with pytest.raises(ValueError):  # no list
        ais.analyse_network(data=dat, processes={})
    with pytest.raises(ValueError):  # no list of ints
        ais.analyse_network(data=dat, processes=[1.5, 0.7])


@jpype_missing
def test_single_source_storage_gaussian():
    n = 1000
    proc_1 = [rn.normalvariate(0, 1) for r in range(n)]  # correlated src
    proc_2 = [rn.normalvariate(0, 1) for r in range(n)]  # correlated src
    # Cast everything to numpy so the idtxl estimator understands it.
    dat = Data(np.array([proc_1, proc_2]), dim_order='ps')
    max_lag = 5
    analysis_opts = {
        'cmi_calc_name': 'jidt_kraskov',
        'n_perm_mi': 22,
        'alpha_mi': 0.05,
        'tail_mi': 'one',
        }
    processes = [1]
    network_analysis = Active_information_storage(max_lag, analysis_opts,
                                                  tau=1)
    res = network_analysis.analyse_network(dat, processes)
    print('AIS for random normal data without memory (expected is NaN): '
          '{0}'.format(res[1]['ais']))
    assert res[1]['ais'] is np.nan, ('Estimator did not return nan for '
                                     'memoryless data.')


@jpype_missing
@opencl_missing
def test_compare_jidt_open_cl_estimator():
    """Compare results from OpenCl and JIDT estimators for AIS calculation."""
    dat = Data()
    dat.generate_mute_data(100, 2)
    max_lag = 5
    analysis_opts = {
        'cmi_calc_name': 'opencl_kraskov',
        'n_perm_mi': 22,
        'alpha_mi': 0.05,
        'tail_mi': 'one',
        }
    processes = [2, 3]
    network_analysis = Active_information_storage(max_lag, analysis_opts,
                                                  tau=1)
    res_opencl = network_analysis.analyse_network(dat, processes)
    analysis_opts['cmi_calc_name'] = 'jidt_kraskov'
    network_analysis = Active_information_storage(max_lag, analysis_opts,
                                                  tau=1)
    res_jidt = network_analysis.analyse_network(dat, processes)
    # Note that I require equality up to three digits. Results become more
    # exact for bigger data sizes, but this takes too long for a unit test.
    print('AIS for MUTE data proc 2 - opencl: {0} and jidt: {1}'.format(
                                    res_opencl[2]['ais'], res_jidt[2]['ais']))
    print('AIS for MUTE data proc 3 - opencl: {0} and jidt: {1}'.format(
                                    res_opencl[3]['ais'], res_jidt[3]['ais']))
    if not (res_opencl[2]['ais'] is np.nan or res_jidt[2]['ais'] is np.nan):
        assert (res_opencl[2]['ais'] - res_jidt[2]['ais']) < 0.05, (
                       'AIS results differ between OpenCl and JIDT estimator.')
    else:
        assert res_opencl[2]['ais'] == res_jidt[2]['ais'], (
                       'AIS results differ between OpenCl and JIDT estimator.')
    if not (res_opencl[3]['ais'] is np.nan or res_jidt[3]['ais'] is np.nan):
        assert (res_opencl[3]['ais'] - res_jidt[3]['ais']) < 0.05, (
                       'AIS results differ between OpenCl and JIDT estimator.')
    else:
        assert res_opencl[3]['ais'] == res_jidt[3]['ais'], (
                       'AIS results differ between OpenCl and JIDT estimator.')
#    np.testing.assert_approx_equal(res_opencl[2]['ais'], res_jidt[2]['ais'],
#                                   significant=3,
#                                   err_msg=('AIS results differ between '
#                                            'OpenCl and JIDT estimator.'))
#    np.testing.assert_approx_equal(res_opencl[3]['ais'], res_jidt[3]['ais'],
#                                   significant=3,
#                                   err_msg=('AIS results differ between '
#                                            'OpenCl and JIDT estimator.'))


if __name__ == '__main__':
    test_analyse_network()
    test_active_information_storage_init()
    # test_single_source_storage_gaussian()
    # test_compare_jidt_open_cl_estimator()
