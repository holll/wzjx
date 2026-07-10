import platform

if platform.system() != 'Windows':
    raise RuntimeError('toIdm 模块仅在 Windows 平台可用（依赖 comtypes）')

import comtypes.client as cc

cc.GetModule(["{ECF21EAB-3AA8-4355-82BE-F777990001DD}", 1, 0])
# not sure about the syntax here, but cc.GetModule will tell you the name of the wrapper it generated
import comtypes.gen.IDManLib as IDMan

idm1 = cc.CreateObject("IDMan.CIDMLinkTransmitter", None, None, IDMan.ICIDMLinkTransmitter2)


def download(url, path, name=None, referrer=None):
    idm1.SendLinkToIDM(url, referrer, None, None, None, None, path, name, 1)
