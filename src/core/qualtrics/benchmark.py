
from collections import defaultdict


import numpy
from core.qualtrics.question import weighted_questions_average


def calculate_group_benchmark_from_raw_responses(filtered_responses, dimensions):
    """ Calculates benchmark on the responses filtered dataset

    Arguments:
        questions {list} -- Array of responses

    Keyword Arguments:
        filtered_responses {array} -- Array of tuple (q_id, q_value, q_weight)
    """
    # each element of the dictionary will be key: list of weighted average by dimension
    responses_benchmarks_by_dimension = defaultdict(list)

    # Loop on a every single response.
    for response in filtered_responses:
        # Create a dict where single response benchmarks aggregated by dimension.
        _, response_benchmarks_by_dimension = calculate_response_benchmark(response)

        for dimension in dimensions:
            benchmark = response_benchmarks_by_dimension.get(dimension, 0)
            responses_benchmarks_by_dimension[dimension].append(benchmark)

    benchmark_by_dimension = {}

    # Create a dict where responses benchmarks aggregated by dimension.
    for dimension in dimensions:
        benchmark_by_dimension[dimension] = numpy.average(responses_benchmarks_by_dimension[dimension])

    return numpy.average(benchmark_by_dimension.values()), benchmark_by_dimension


def calculate_response_benchmark(response_questions, dimensions_weights=None):

    # Create a dict where single response questions are aggregated by dimension.
    questions_by_dimension = defaultdict(list)

    for question in response_questions:
        if question[3]:
            questions_by_dimension[question[3]].append(question)

    # Create a dict where single response benchmarks aggregated by dimension.
    benchmark_by_dimension = {}
    for dimension, questions in questions_by_dimension.iteritems():
        benchmark_by_dimension[dimension] = weighted_questions_average(questions)

    ordered_weights = None
    benchmark_by_dimension_values = []
    if dimensions_weights:
        ordered_weights = []
        for dim, val in benchmark_by_dimension.items():
            benchmark_by_dimension_values.append(val)
            ordered_weights.append(dimensions_weights[dim])
    else:
        benchmark_by_dimension_values = benchmark_by_dimension.values()
    return numpy.average(benchmark_by_dimension_values, weights=ordered_weights), benchmark_by_dimension


def _by_dimension(dmb_d_list, aggregated_function, dimensions):
    """
    Given a `dmb_d_list` and an `aggregated_function`, returns a dictionary
    where the `aggregated_function` is applied for each `settings.DIMENSION`
    """
    dmb_d_by_dimension = defaultdict(list)
    benchmark_by_dimension = {}

    for dmb_d in dmb_d_list:

        for dimension in dimensions:
            benchmark = dmb_d.get(dimension, 0)
            dmb_d_by_dimension[dimension].append(benchmark)

    for dimension in dimensions:
        benchmark_by_dimension[dimension] = aggregated_function(dmb_d_by_dimension[dimension])

    return benchmark_by_dimension


def calculate_group_benchmark(dmb_d_list, dimensions, dmb_values=None):
    """ Calculates benchmark on the dmb_d_list dataset."""
    benchmark_by_dimension = _by_dimension(dmb_d_list, numpy.average, dimensions)
    dmb = None
    if dmb_values is not None:
        # case for NEWS
        dmb = numpy.average(dmb_values)
    else:
        dmb = numpy.average(benchmark_by_dimension.values())

    return dmb, benchmark_by_dimension


def calculate_best_practice(dmb_d_list, dimensions, dmb_values=None):
    """ Calculates best practice on the dmb_d_list dataset."""
    benchmark_by_dimension = _by_dimension(dmb_d_list, numpy.amax, dimensions)
    dmb = None
    if dmb_values is not None:
        # case for NEWS
        dmb = numpy.amax(dmb_values)
    else:
        dmb = numpy.average(benchmark_by_dimension.values())

    return dmb, benchmark_by_dimension
