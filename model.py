from functools import reduce
import torch
from torch import nn, autograd
import torchvision.models as models
from torch.nn import functional as F


import torch.nn as nn
import math


__all__ = ['preresnet']

def conv3x3(in_planes, out_planes, stride=1):
    "3x3 convolution with padding"
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride,
                     padding=1, bias=False)


class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, inplanes, planes, stride=1, downsample=None):
        super(BasicBlock, self).__init__()
        self.bn1 = nn.BatchNorm2d(inplanes)
        self.relu = nn.ReLU(inplace=True)
        self.conv1 = conv3x3(inplanes, planes, stride)
        self.bn2 = nn.BatchNorm2d(planes)
        self.conv2 = conv3x3(planes, planes)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x

        out = self.bn1(x)
        out = self.relu(out)
        out = self.conv1(out)

        out = self.bn2(out)
        out = self.relu(out)
        out = self.conv2(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual

        return out


class Bottleneck(nn.Module):
    expansion = 4

    def __init__(self, inplanes, planes, stride=1, downsample=None):
        super(Bottleneck, self).__init__()
        self.bn1 = nn.BatchNorm2d(inplanes)
        self.conv1 = nn.Conv2d(inplanes, planes, kernel_size=1, bias=False)
        self.bn2 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=stride,
                               padding=1, bias=False)
        self.bn3 = nn.BatchNorm2d(planes)
        self.conv3 = nn.Conv2d(planes, planes * 4, kernel_size=1, bias=False)
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x

        out = self.bn1(x)
        out = self.relu(out)
        out = self.conv1(out)

        out = self.bn2(out)
        out = self.relu(out)
        out = self.conv2(out)

        out = self.bn3(out)
        out = self.relu(out)
        out = self.conv3(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual

        return out


class PreResNet(nn.Module):

    def __init__(self, depth, num_classes=1000, block_name='Bottleneck'):
        super(PreResNet, self).__init__()
        # Model type specifies number of layers for CIFAR-10 model
        if block_name.lower() == 'basicblock':
            assert (depth - 2) % 6 == 0, 'When use basicblock, depth should be 6n+2, e.g. 20, 32, 44, 56, 110, 1202'
            n = (depth - 2) // 6
            block = BasicBlock
        elif block_name.lower() == 'bottleneck':
            assert (depth - 2) % 9 == 0, 'When use bottleneck, depth should be 9n+2, e.g. 20, 29, 47, 56, 110, 1199'
            n = (depth - 2) // 9
            block = Bottleneck
        else:
            raise ValueError('block_name shoule be Basicblock or Bottleneck')

        self.inplanes = 16
        self.conv1 = nn.Conv2d(1, 16, kernel_size=3, padding=1,
                               bias=False)
        self.layer1 = self._make_layer(block, 16, n)
        self.layer2 = self._make_layer(block, 32, n, stride=2)
        self.layer3 = self._make_layer(block, 64, n, stride=2)
        self.bn = nn.BatchNorm2d(64 * block.expansion)
        self.relu = nn.ReLU(inplace=True)
        #self.avgpool = nn.AvgPool2d(8)
        self.avgpool = nn.AdaptiveAvgPool2d((1,1))  #只在W方向上做池化，因为数据是15*10240 
        self.fc = nn.Linear(64 * block.expansion, num_classes)

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def _make_layer(self, block, planes, blocks, stride=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                nn.Conv2d(self.inplanes, planes * block.expansion,
                          kernel_size=1, stride=stride, bias=False),
            )

        layers = []
        layers.append(block(self.inplanes, planes, stride, downsample))
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            layers.append(block(self.inplanes, planes))

        return nn.Sequential(*layers)

    def forward(self, x, return_features=False, return_attentions=False):
        x = self.conv1(x)

        f1 = self.layer1(x)  # 32x32
        f2 = self.layer2(f1)  # 16x16
        f3 = self.layer3(f2)  # 8x8
        x = self.bn(f3)
        x = self.relu(x)

        x = self.avgpool(x)
        x = x.view(x.size(0), -1)
        logits = self.fc(x)

        features = x.view(x.size(0), -1)    
        logits = self.fc(features)  # [B, C]

        if return_attentions==True:
             return logits, [f1, f2, f3]

        if return_features==True:
            return logits, features
        
        return logits


def preresnet(**kwargs):
    """
    Constructs a ResNet model.
    """
    return PreResNet(**kwargs)


# class BiasLayer(nn.Module):
#     def __init__(self):
#         super(BiasLayer, self).__init__()
#         self.alpha = nn.Parameter(torch.ones(1, requires_grad=True, device="cuda"))
#         self.beta = nn.Parameter(torch.zeros(1, requires_grad=True, device="cuda"))
#     def forward(self, x):
#         return self.alpha * x + self.beta
#     def printParam(self, i):
#         print(f"in layer {i}, alpha = {self.alpha.item()}, beta = {self.beta.item()}")

class BiasLayer(nn.Module):
    def __init__(self, num_classes):
        super(BiasLayer, self).__init__()
        # 每个class一个alpha, beta  (IL2M)
        self.alpha = nn.Parameter(torch.ones(num_classes, device="cuda"))
        self.beta = nn.Parameter(torch.zeros(num_classes, device="cuda"))
        self.num_classes = num_classes
        # weight align scale (WA)
        self.weight_align_scale = 1.0

    def forward(self, x):
        # x shape: (batch_size, num_classes)
        # Expand alpha/beta to match batch_size
        # shape: (1, num_classes) → broadcast to (batch_size, num_classes)
        return self.alpha * x * self.weight_align_scale + self.beta

    def update_weight_align(self, classifier):
        # classifier: nn.Linear
        with torch.no_grad():
            weight_norm = classifier.weight.norm(dim=1)  # shape (num_classes,)
            old_classes = torch.arange(self.num_classes, device="cuda")
            # mean norm over all classes
            mean_norm = weight_norm.mean()
            self.weight_align_scale = 1.0 / mean_norm.item()
            print(f"[Weight Align] Applied scale factor: {self.weight_align_scale:.4f}")

    def printParam(self, i):
        print(f"[BiasLayer] layer {i}")
        print(f"  alpha (per class): {self.alpha.detach().cpu().numpy()}")
        print(f"  beta  (per class): {self.beta.detach().cpu().numpy()}")
        print(f"  weight_align_scale: {self.weight_align_scale:.4f}")