-- SmartThings cosock-compatible MQTT I/O. Avoid zero-timeout bulk reads.
local M = {}
function M.send(sock, data)
  local n, err = sock:send(data)
  if n == true or n == #data then return end
  if type(n) == "number" then error("short_write") end
  if err == "timeout" then error("send_timeout") end
  if err == "closed" then error("send_closed") end
  error("send_failed")
end

function M.read(sock)
  local data, err, partial = sock:receive(1)
  if data ~= nil and type(data) ~= "string" then error("invalid_read_type") end
  if type(data) == "string" and #data > 0 then return data end
  if err == "closed" then error("receive_closed") end
  if err ~= nil and err ~= "timeout" then error("receive_failed") end
  if type(partial) == "string" and #partial > 0 then return partial end
  return ""
end
return M
