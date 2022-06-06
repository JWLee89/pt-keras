import logging

import torch
import torch.nn as nn
import tensorflow as tf
from torchvision.models.efficientnet import efficientnet_b0


class Block(nn.Module):
    def __init__(self):
        super().__init__()


class DummyModel(nn.Module):
    def __init__(self):
        super().__init__()
        # These can all be found using named_modules() or children()
        self.conv = nn.Sequential(
            nn.Conv2d(3, 32, (3, 3), stride=(1, 1), padding=(1, 1), groups=1, bias=True),
            nn.SiLU(),
            # Downsample
            nn.Conv2d(32, 64, (3, 3), stride=(1, 1), padding=(1, 1), dilation=(1, 1), groups=1, bias=True),
            nn.SiLU(),

            # nn.Conv2d(64, 128, (1, 1), stride=(2, 2), padding=(0, 0), groups=1, dilation=(1, 1), bias=False),

            # nn.Conv2d(3, 32, (3, 3), stride=(2, 2), padding=(1, 1), groups=1, bias=True),
            # nn.SiLU(),
            # nn.Conv2d(32, 32, (3, 3), stride=(1, 1), padding=(1, 1), groups=32, dilation=(1, 1),  bias=True),
            # nn.SiLU(),
            # nn.ConvTranspose2d(32, 64, (3, 3), (2, 2), padding=(1, 1))
        )

        self.avg_pool = nn.AdaptiveAvgPool2d(1)

        # self.conv = nn.Sequential(
        #     nn.Conv2d(3, 16, (1, 1), (2, 2), bias=True),
        #     # nn.BatchNorm2d(16),
        #     # nn.ConvTranspose2d(16, 32, kernel_size=(3, 3), stride=(2, 2))
        # )

    def forward(self, X):
        # we can retrieve these operations via .modules(), named_modules(), children(), etc.
        output = self.conv(X)
        new_path = self.avg_pool(output)
        return new_path
        # return output[:, :, 2, 4]


if __name__ == '__main__':
    from pt2keras import Pt2Keras
    from copy import deepcopy
    import numpy as np
    # Test pt2keras on EfficientNet_b0
    model = efficientnet_b0(pretrained=True).eval()
    height_width = 32

    # Generate dummy inputs
    x_keras = tf.random.normal((1, height_width, height_width, 3))
    # input dimensions for PyTorch are BCHW, whereas TF / Keras default is BHWC
    x_pt = torch.from_numpy(deepcopy(x_keras.numpy())).permute(0, 3, 1, 2)

    print(f'pt shape: {x_pt.shape}, x_keras.shape: {x_keras.shape}')

    # Convert the model
    converter = Pt2Keras(model, x_pt.shape)
    # Set to debug to read information
    converter.set_logging_level(logging.DEBUG)

    keras_model = converter.convert()

    # Make PT model the same input dimension as Keras
    # If the output is >= 4 dimensional
    pt_output = model(x_pt).cpu().detach().numpy()
    keras_output = keras_model(x_keras).numpy()
    # Mean average diff over all axis

    average_diff = np.mean(np.mean([pt_output, keras_output]))
    print(f'pytorch: {pt_output.shape}')
    print(f'keras: {keras_output.shape}')
    # The differences will be precision errors from multiplication / division
    print(f'Mean average diff: {average_diff}')

    output_is_approximately_equal = np.allclose(pt_output, keras_output, atol=1e-4)
    assert output_is_approximately_equal, f'PyTorch output and Keras output is different. ' \
                                          f'Mean difference: {average_diff}'

    # See for yourself
    # print(keras_output)
    # print(pt_output)
    keras_model.save('model.h5')
