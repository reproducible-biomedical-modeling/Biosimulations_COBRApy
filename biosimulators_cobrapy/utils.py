""" Utilities for working with COBRApy

:Author: Jonathan Karr <karr@mssm.edu>
:Date: 2020-12-31
:Copyright: 2020, BioSimulators Team
:License: MIT
"""

from biosimulators_utils.report.data_model import DataGeneratorVariableResults
from biosimulators_utils.sedml.data_model import DataGeneratorVariable  # noqa: F401
from biosimulators_utils.utils.core import validate_str_value, parse_value
import cobra  # noqa: F401
import numpy
import re

__all__ = ['set_simulation_method_arg', 'validate_variables', 'get_results_of_variables']


def set_simulation_method_arg(method_props, argument_change, model, model_method_kw_args):
    """ Set the value of an argument of a simulation method based on a SED
    algorithm parameter change

    Args:
        method_props (:obj:`dict`): properties of the simulation method
        argument_change (:obj:`AlgorithmParameterChange`): algorithm parameter change
        model (:obj:`cobra.core.model.Model`)
        model_method_kw_args (:obj:`dict`): keyword arguments for the simulation method
            for the model

    Raises:
        :obj:`NotImplementedError`: if the simulation method doesn't support the parameter
        :obj:`ValueError`: if the new value is not a valid value of the parameter
    """
    parameter_kisao_id = argument_change.kisao_id
    parameter = method_props['parameters'].get(parameter_kisao_id, None)
    if parameter is None:
        msg = "".join([
            "{} ({}) does not support parameter `{}`. ".format(
                method_props['name'], method_props['kisao_id'], argument_change.kisao_id),
            "The parameters of {} must have one of the following KiSAO ids:\n  - {}".format(
                method_props['name'],
                '\n  - '.join(
                    '{} ({}): {}'.format(kisao_id, parameter['name'], parameter['description'])
                    for kisao_id, parameter in method_props['parameters'].items())),
        ])
        raise NotImplementedError(msg)

    value = argument_change.new_value
    if not validate_str_value(value, parameter['type']):
        msg = "`{}` is not a valid value for parameter {} ({}) of {} ({})".format(
            value, parameter['name'], parameter_kisao_id,
            method_props['name'], method_props['kisao_id'])
        raise ValueError(msg)
    enum = parameter.get('enum', None)
    if enum:
        if value.lower() not in enum.__members__:
            msg = ("`{}` is not a valid value for parameter {} ({}) of {} ({}). "
                   "The value of {} must be one of the following:\n  - {}").format(
                value, parameter['name'], parameter_kisao_id,
                method_props['name'], method_props['kisao_id'],
                method_props['name'],
                '\n  - '.join(sorted('`' + value + '`' for value in enum.__members__.keys())))
            raise ValueError(msg)

    parsed_value = parse_value(value, parameter['type'])
    if enum:
        parsed_value = enum[value.lower()].value

    if parameter.get('alg_arg', None) == 'reaction_list':
        reaction_ids = set(reaction.id for reaction in model.reactions)
        parsed_value = set(parsed_value)
        invalid_values = parsed_value.difference(reaction_ids)
        if invalid_values:
            msg = (
                'Some of the values of {} ({}) of {} ({}) are not SBML ids of reactions:\n  - {}\n\n'
                'The values of {} should be drawn from the following list of the SMBL ids of the reactions of the model:\n  - {}'
            ).format(
                parameter['name'], parameter_kisao_id,
                method_props['name'], method_props['kisao_id'],
                '\n  - '.join(sorted('`' + value + '`' for value in invalid_values)),
                parameter['name'],
                '\n  - '.join(sorted('`' + reaction.id + '`' for reaction in model.reactions)),
            )
            raise ValueError(msg)
        parsed_value = sorted(parsed_value)

    if 'alg_arg' in parameter:
        model_method_kw_args[parameter['alg_arg']] = parsed_value
    else:
        setattr(model, parameter['model_arg'], parsed_value)


def validate_variables(method, variables):
    """ Validate the desired output variables of a simulation

    Args:
        method (:obj:`dict`): properties of desired simulation method
        variables (:obj:`list` of :obj:`DataGeneratorVariable`): variables that should be recorded
    """
    invalid_symbols = set()
    invalid_targets = set()
    for variable in variables:
        if variable.symbol:
            invalid_symbols.add(variable.symbol)

        else:
            valid = False
            for variable_pattern in method['variables']:
                if re.match(variable_pattern['target'], variable.target):
                    valid = True
                    break

            if not valid:
                invalid_targets.add(variable.target)

    if invalid_symbols:
        raise NotImplementedError("{} ({}) doesn't support variables with symbols".format(
            method['name'], method['kisao_id']))

    if invalid_targets:
        msg = (
            "{} ({}) doesn't support variables with the following target XPATHs:\n  - {}\n\n"
            "The targets of variables should match one of the following patterns of XPATHs:\n  - {}"
        ).format(
            method['name'], method['kisao_id'],
            '\n  - '.join(sorted('`' + target + '`' for target in invalid_targets)),
            '\n  - '.join(sorted('{}: `{}`'.format(
                variable_pattern['description'], variable_pattern['target'])
                for variable_pattern in method['variables']))
        )
        raise ValueError(msg)


def get_results_of_variables(method, variables, target_x_paths_ids, solution):
    """ Get the results of the desired variables

    Args:
        method (:obj:`dict`): properties of desired simulation method
        variables (:obj:`list` of :obj:`DataGeneratorVariable`): variables that should be recorded
        target_x_paths_ids (:obj:`dict` of :obj:`str` to :obj:`str`): dictionary that maps each XPath to the
            value of the attribute of the object in the XML file that matches the XPath
        solution (:obj:`cobra.core.solution.Solution`): solution of method

    Returns:
        :obj:`DataGeneratorVariableResults`: the results of desired variables
    """
    variable_results = DataGeneratorVariableResults()

    for variable in variables:
        target = variable.target
        for variable_pattern in method['variables']:
            if re.match(variable_pattern['target'], target):
                variable_target_id = None
                if variable_pattern['target_type'] in ['reaction', 'species']:
                    variable_target_id = target_x_paths_ids[target]

                result = variable_pattern['get_result'](solution, variable_target_id)

                break

        variable_results[variable.id] = numpy.array(result)

    return variable_results
