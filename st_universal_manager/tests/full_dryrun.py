import sys
sys.path.insert(0,"/opt")
import manager as m
cfg=m.mqtt_config("192.168.0.19",1883,"test-user","test-password","home")
plan=[{"family":n,"key":m.load_build().package_key(n),"driver_id":None,"mode":"new"} for n in m.FAMILIES]
class NoCLI:
 def __getattr__(self,n):raise AssertionError("Dry run must not access network CLI")
m.build_and_deploy(NoCLI(),"","",plan,cfg,False,print)
