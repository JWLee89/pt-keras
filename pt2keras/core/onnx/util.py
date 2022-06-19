import logging
import typing as t

import numpy as np
import onnx.checker
import onnx.helper
import onnxruntime
import tensorflow as tf
from tensorflow import keras
import torch
import torch.nn as nn


_LOGGER = logging.getLogger('util::Test')


def keras_4d_to_pt_shape(input_data: np.ndarray) -> t.Tuple:
    """
    Given an input data, if it is a 4d input,
    such as an image or conv intermediate feature,
    we assume that input data is Keras format
    (B, H, W, C) and we will convert to PyTorch:
    (B, C, H, W).
    Args:
        input_data: The input data we will be transforming.
    Returns:
        The converted data
    """
    if len(input_data.shape) != 4:
        return input_data.shape

    if isinstance(input_data, np.ndarray):
        #  (B, H, W, C) ->  (B, C, H, W)
        output_data = input_data.transpose((0, 3, 1, 2))
    elif keras.backend.is_keras_tensor(input_data):
        output_data = tf.transpose(input_data, (0, 3, 1, 2))
    else:
        raise ValueError('keras_4d_to_pt only accepts Numpy ndarray or KerasTensor')

    return output_data.shape


def test_model_output(source_model: t.Union[nn.Module, onnxruntime.InferenceSession],
                      keras_model: tf.keras.Model,
                      pt_input_shape: t.Tuple,
                      keras_input_shape: t.Tuple,
                      atol=1e-4) -> None:
    """
    Compare and test the PyTorch and Keras model for output equality.
    An error will be asserted if the generated inputs are not close
    or are of different dimensions.
    Args:
        source_model: The source PyTorch / Onnx model
        keras_model: The target / generated Keras model
        pt_input_shape: The dimension of the PyTorch input data
        keras_input_shape: The dimension of the Keras input data
        atol: The absolute tolerance parameter specified in numpy.
        See numpy documentation for more information
    """
    # Create TensorFlow input
    random_tensor_source = np.random.randn(*pt_input_shape).astype(np.float32)
    random_tensor_keras = random_tensor_source
    if len(random_tensor_source.shape) == 4:
        random_tensor_keras = random_tensor_keras.transpose((0, 2, 3, 1))

    x_keras = tf.convert_to_tensor(random_tensor_keras)
    output_keras = keras_model(x_keras)

    # Handle inputs :)
    # PyTorch / onnx inference
    if isinstance(source_model, nn.Module):
        x_pt = torch.from_numpy(random_tensor_source)
        output_source = source_model(x_pt)
    # Onnxruntime inference
    elif isinstance(source_model, onnxruntime.InferenceSession):
        output_source = source_model.run(None, {'input_0': random_tensor_source})
        # Onnx output is a list, so we flatten it if output length is 1
        if len(output_source) == 1:
            output_source = output_source[0]
    else:
        raise ValueError('Source model must be a PyTorch model on onnxruntime InferenceSession')

    # For multiple outputs
    if isinstance(output_source, (t.Tuple, t.List)):
        for source_tensor, keras_tensor in zip(output_source, output_keras):
            if isinstance(source_tensor, torch.Tensor):
                source_tensor = source_tensor.detach().cpu().numpy()
            test_equality(source_tensor, keras_tensor.numpy(), atol)
    # Single outputs
    else:
        if isinstance(output_source, torch.Tensor):
            output_source = output_source.detach().cpu().numpy()
        test_equality(output_source, output_keras, atol)


def test_equality(output_source: np.ndarray, output_keras: np.ndarray, atol: float = 1e-4):
    """
    Test the outputs of the two models for equality.
    Args:
        output_source: The output of a PyTorch model
        output_keras: The output of the converted Keras model
        atol: The absolute tolerance parameter specified in numpy.
    """
    if len(output_source.shape) == 4:
        output_source = output_source.transpose((0, 2, 3, 1))

    print(f'source shape: {output_source.shape}, keras shape: {output_keras.shape}')

    # batch dimension may have been removed for PyTorch model using flatten
    if len(output_source.shape) == len(output_keras.shape) - 1:
        for pt_dim, keras_dim in zip(output_source.shape, output_keras.shape[1:]):
            assert pt_dim == keras_dim, 'Batch dimension may have been removed from PyTorch model, but ' \
                                        f'the input dimensions still dont match. ' \
                                        f'PT shape: {output_source.shape}' \
                                        f'Keras shape: {output_keras.shape}'
        _LOGGER.warning('Batch dimension may have possibly been removed from PyTorch model. '
                        'Does your model use nn.Flatten() or torch.flatten() with start_dim=1 ?')
    else:
        assert output_source.shape == output_keras.shape, 'PyTorch and Keras model output shape should be equal. ' \
                                                      f'PT shape: {output_source.shape}, ' \
                                                      f'Keras shape: {output_keras.shape}'

    # Average diff over all axis
    average_diff = np.mean(output_source - output_keras)

    output_is_approximately_equal = np.allclose(output_source, output_keras, atol=atol)
    assert output_is_approximately_equal, f'PyTorch output and Keras output is different. ' \
                                          f'Mean difference: {average_diff}'


def get_tensor_data(initializer: onnx.TensorProto) -> None:
    """
    Given an onnx tensor, return the data / weights stored
    """
    if initializer.data_type == onnx.TensorProto.DataType.FLOAT:
        return initializer.float_data
    elif initializer.data_type == onnx.TensorProto.DataType.INT32:
        return initializer.int32_data
    elif initializer.data_type == onnx.TensorProto.DataType.INT64:
        return initializer.int64_data
    elif initializer.data_type == onnx.TensorProto.DataType.DOUBLE:
        return initializer.double_data
    elif initializer.data_type == onnx.TensorProto.DataType.UINT64:
        return initializer.uint64_data
    else:
        raise NotImplementedError


def tensor_proto_to_tf_dtype(tensor_data_type: int):
    """
    Given an tensor proto data type value (int), convert it to appropriate
    tensorflow data type
    """
    if tensor_data_type == onnx.TensorProto.DataType.FLOAT:
        return tf.float32
    elif tensor_data_type == onnx.TensorProto.DataType.INT32:
        return tf.int32
    elif tensor_data_type == onnx.TensorProto.DataType.INT64:
        return tf.int64
    elif tensor_data_type == onnx.TensorProto.DataType.DOUBLE:
        return tf.float64
    elif tensor_data_type == onnx.TensorProto.DataType.UINT64:
        return tf.uint64
    else:
        raise NotImplementedError


class NodeProperties:
    name = 'name'
    shape = 'shape'


def get_graph_input_shape(graph: onnx.GraphProto,
                          transpose_matrix: t.Union[t.List, t.Tuple]) -> t.List[t.Dict]:
    """
    Args:
        graph: The graph we want t
        transpose_matrix:

    Returns:
        A list containing information on the graph input node
    """
    shape_info = []
    for node in graph.input:
        data = _add_node_property(node, transpose_matrix)
        shape_info.append(data)
    return shape_info


def to_tf(obj, fake_input_layer=None, name=None):
    """
    Convert to Keras Constant if needed
    @Credit onnx2keras for this function
    https://github.com/gmalivenko/onnx2keras/blob/45c81f221bb4228751abb061cb24d473bb74a8e8/onnx2keras/utils.py#L26

    Args:
        obj: numpy / tf type
        fake_input_layer: fake input layer to add constant
    Returns:
        Tf constant
    """
    if isinstance(obj, np.ndarray):
        # Downcast
        if obj.dtype == np.int64:
            obj = np.int32(obj)

        def target_layer(_, inp=obj, dtype=obj.dtype.name):
            import numpy as np
            import tensorflow as tf
            if not isinstance(inp, (np.ndarray, np.generic)):
                inp = np.array(inp, dtype=dtype)
            return tf.constant(inp, dtype=inp.dtype)
        lambda_layer = keras.layers.Lambda(target_layer, name=name)
        output = lambda_layer(fake_input_layer)

        return output
    else:
        return obj


def get_graph_output_shape(graph: onnx.GraphProto,
                           transpose_matrix: t.Union[t.List, t.Tuple] = None) -> t.List[t.Dict]:
    """
    Args:
        graph: The graph we want t
        transpose_matrix:

    Returns:
        A list containing information on the graph output node
    """
    shape_info = []
    for node in graph.input:
        data = _add_node_property(node, transpose_matrix)
        shape_info.append(data)
    return shape_info


def _add_node_property(node, transpose_matrix: t.Union[t.List, t.Tuple] = None) -> t.Dict:
    data = {NodeProperties.name: node.name}
    input_shape = []
    # Grab dimension information
    dimensions = node.type.tensor_type.shape.dim
    if transpose_matrix:
        for index in transpose_matrix:
            input_shape.append(dimensions[index].dim_value)
    else:
        for dim in dimensions:
            input_shape.append(dim.dim_value)
    # Convert to appropriate format
    data[NodeProperties.shape] = input_shape
    return data


def generate_node_key(node: onnx.NodeProto):
    final_key = ''
    input_str = ''
    for input_name in node.input:
        input_str += f'{input_name}_'

    if input_str:
        final_key += 'INPUTINFO-'
        final_key += input_str

    output_str = ''
    for output_name in node.output:
        output_str += f'{output_name}_'

    # remove trailing '_'
    if output_str:
        final_key += 'OUTPUTINFO-'
        final_key += output_str

    if final_key.endswith('_'):
        final_key = final_key[:-1]

    return final_key
