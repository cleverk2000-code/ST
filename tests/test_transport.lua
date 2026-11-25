package.path = "edge/st-local-edge/src/?.lua;" .. package.path
local t = require "transport"
local w = require "wire"
local function sock(value, err, partial)
  return {receive=function(_, n) assert(n==1); return value,err,partial end}
end
assert(t.read(sock(string.char(0x20))) == string.char(0x20))
assert(t.read(sock(nil,"timeout")) == "")
assert(t.read(sock(nil,nil)) == "")
assert(t.read(sock(nil,"timeout","x")) == "x")
assert(not pcall(t.read,sock(nil,"closed")))
assert(not pcall(t.read,sock(nil,"other")))
local data="abc"
assert(pcall(t.send,{send=function() return 3 end},data))
assert(pcall(t.send,{send=function() return true end},data))
assert(not pcall(t.send,{send=function() return 1 end},data))
assert(not pcall(t.send,{send=function() return nil,"timeout",1 end},data))
-- CONNACK and SUBACK delivered one byte at a time, interspersed with idle reads.
local input=string.char(0x20,2,0,0,0x90,4,0,1,1,1)
local buf,frames="",{}
for i=1,#input do
  buf=buf..t.read(sock(nil,"timeout"))
  buf=buf..t.read(sock(input:sub(i,i)))
  local h,b,rest=w.pop(buf)
  if h then frames[#frames+1]={h,b}; buf=rest end
end
assert(#frames==2 and frames[1][1]==0x20 and frames[2][1]==0x90 and buf=="")
print("MQTT transport tests passed")
