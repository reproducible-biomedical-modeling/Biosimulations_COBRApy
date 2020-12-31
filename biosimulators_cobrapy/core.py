""" Methods for using COBRApy to execute SED tasks in COMBINE archives and save their outputs

:Author: Jonathan Karr <karr@mssm.edu>
:Date: 2020-12-31
:Copyright: 2020, BioSimulators Team
:License: MIT
"""

from .data_model import KISAO_ALGORITHMS_PARAMETERS_MAP
from .utils import set_simulation_method_arg, validate_variables, get_results_of_variables
from biosimulators_utils.combine.exec import exec_sedml_docs_in_archive
from biosimulators_utils.plot.data_model import PlotFormat  # noqa: F401
from biosimulators_utils.report.data_model import ReportFormat, DataGeneratorVariableResults  # noqa: F401
from biosimulators_utils.sedml.data_model import (Task, ModelLanguage, SteadyStateSimulation,  # noqa: F401
                                                  DataGeneratorVariable)
from biosimulators_utils.sedml import validation
import cobra.io

__all__ = [
    'exec_sedml_docs_in_combine_archive',
    'exec_sed_task',
]


def exec_sedml_docs_in_combine_archive(archive_filename, out_dir,
                                       report_formats=None, plot_formats=None,
                                       bundle_outputs=None, keep_individual_outputs=None):
    """ Execute the SED tasks defined in a COMBINE/OMEX archive and save the outputs

    Args:
        archive_filename (:obj:`str`): path to COMBINE/OMEX archive
        out_dir (:obj:`str`): path to store the outputs of the archive

            * CSV: directory in which to save outputs to files
              ``{ out_dir }/{ relative-path-to-SED-ML-file-within-archive }/{ report.id }.csv``
            * HDF5: directory in which to save a single HDF5 file (``{ out_dir }/reports.h5``),
              with reports at keys ``{ relative-path-to-SED-ML-file-within-archive }/{ report.id }`` within the HDF5 file

        report_formats (:obj:`list` of :obj:`ReportFormat`, optional): report format (e.g., csv or h5)
        plot_formats (:obj:`list` of :obj:`PlotFormat`, optional): report format (e.g., pdf)
        bundle_outputs (:obj:`bool`, optional): if :obj:`True`, bundle outputs into archives for reports and plots
        keep_individual_outputs (:obj:`bool`, optional): if :obj:`True`, keep individual output files
    """
    exec_sedml_docs_in_archive(archive_filename, exec_sed_task, out_dir,
                               apply_xml_model_changes=True,
                               report_formats=report_formats,
                               plot_formats=plot_formats,
                               bundle_outputs=bundle_outputs,
                               keep_individual_outputs=keep_individual_outputs)


def exec_sed_task(task, variables):
    ''' Execute a task and save its results

    Args:
       task (:obj:`Task`): task
       variables (:obj:`list` of :obj:`DataGeneratorVariable`): variables that should be recorded

    Returns:
        :obj:`DataGeneratorVariableResults`: results of variables

    Raises:
        :obj:`ValueError`: if the task or an aspect of the task is not valid, or the requested output variables
            could not be recorded
        :obj:`NotImplementedError`: if the task is not of a supported type or involves an unsuported feature
    '''
    validation.validate_task(task)
    validation.validate_model_language(task.model.language, ModelLanguage.SBML)
    validation.validate_model_change_types(task.model.changes, ())
    validation.validate_simulation_type(task.simulation, (SteadyStateSimulation, ))
    validation.validate_uniform_time_course_simulation(task.simulation)
    validation.validate_data_generator_variables(variables)
    target_x_paths_ids = validation.validate_data_generator_variable_xpaths(variables, task.model.source, attr='id')

    # Read the model
    model = cobra.io.read_sbml_model(task.model.source)

    # Load the simulation method specified by ``simulation.algorithm``
    simulation = task.simulation
    algorithm_kisao_id = simulation.algorithm.kisao_id
    method_props = KISAO_ALGORITHMS_PARAMETERS_MAP.get(algorithm_kisao_id, None)
    if method_props is None:
        msg = "".join([
            "Algorithm with KiSAO id '{}' is not supported. ".format(algorithm_kisao_id),
            "Algorithm must have one of the following KiSAO ids:\n  - {}".format('\n  - '.join(
                '{}: {}'.format(kisao_id, method_props['name'])
                for kisao_id, method_props in KISAO_ALGORITHMS_PARAMETERS_MAP.items())),
        ])
        raise NotImplementedError(msg)

    # set up method parameters specified by ``simulation.algorithm.changes``
    method_kw_args = {}
    for method_arg_change in simulation.algorithm.changes:
        set_simulation_method_arg(method_props, method_arg_change, model, method_kw_args)

    # validate variables
    validate_variables(method_props, variables)

    # execute simulation
    solution = method_props['method'](model, **method_kw_args)

    # check that solution was optimal
    if solution.status != 'optimal':
        raise cobra.exceptions.OptimizationError("A solution could not be found. The solver status was '{}'.".format(
            solution.status))

    # Save a report of the results of the simulation
    return get_results_of_variables(method_props, variables, target_x_paths_ids, solution)
