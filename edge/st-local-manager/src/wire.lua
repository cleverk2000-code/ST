-- Minimal MQTT 3.1.1 wire codec. Original implementation, no external dependencies.
local M = {}
local MAX = 65536

function M.u16(n)
  assert(n >= 0 and n <= 65535 and n % 1 == 0)
  return string.char(math.floor(n / 256), n % 256)
end

function M.str(s)
  return M.u16(#s) .. s
end

function M.frame(header, body)
  assert(#body <= MAX, "packet too large")
  local n, bytes = #body, {}
  repeat
    local b = n % 128
    n = math.floor(n / 128)
    bytes[#bytes + 1] = string.char(b + (n > 0 and 128 or 0))
  until n == 0
  return string.char(header) .. table.concat(bytes) .. body
end

-- Clean session, retained QoS0 Last Will; no queued stale commands.
function M.connect(id, user, password, availability)
  assert(user ~= "" and password ~= "", "credentials required")
  local body = M.str("MQTT") .. string.char(4, 0xE6) .. M.u16(20)
  body = body .. M.str(id) .. M.str(availability) .. M.str("offline")
  return M.frame(0x10, body .. M.str(user) .. M.str(password))
end

function M.subscribe(...)
  local body = M.u16(1)
  for _, topic in ipairs({...}) do body = body .. M.str(topic) .. string.char(1) end
  return M.frame(0x82, body)
end

function M.publish(topic, payload, retain)
  return M.frame(retain and 0x31 or 0x30, M.str(topic) .. payload)
end

function M.pop(buffer)
  if #buffer < 2 then return nil end
  local length, multiplier = 0, 1
  for i = 2, 5 do
    local b = buffer:byte(i)
    if not b then return nil end
    length = length + (b % 128) * multiplier
    assert(length <= MAX, "packet too large")
    if b < 128 then
      if #buffer < i + length then return nil end
      return buffer:byte(1), buffer:sub(i + 1, i + length), buffer:sub(i + length + 1)
    end
    multiplier = multiplier * 128
  end
  error("invalid remaining length")
end

function M.decode_publish(header, body)
  assert(#body >= 2, "truncated topic")
  local len = body:byte(1) * 256 + body:byte(2)
  assert(len > 0 and #body >= 2 + len, "invalid topic")
  local topic, pos = body:sub(3, 2 + len), 3 + len
  local qos = math.floor(header / 2) % 4
  local packet_id
  assert(qos <= 1, "unsupported QoS")
  if qos == 1 then
    assert(#body >= pos + 1, "truncated packet id")
    packet_id = body:sub(pos, pos + 1)
    assert(packet_id ~= "\0\0", "invalid packet id")
    pos = pos + 2
  end
  return topic, body:sub(pos), packet_id, header % 2 == 1
end

function M.puback(id)
  return M.frame(0x40, id)
end

function M.command(prefix, topic, payload, retained, cover)
  if retained or payload ~= "pushed" then return nil end
  if topic == prefix .. "/on" then return "commandOn" end
  if topic == prefix .. "/off" then return "commandOff" end
  if cover and topic == prefix .. "/stop" then return "commandStop" end
end

function M.shade_state(code)
  return ({[0]="closed",[1]="open",[2]="opening",[3]="closing",[4]="partially open",[5]="paused",[6]="unknown"})[code]
end

function M.uuid(s)
  if type(s) ~= "string" or not s:match("^%x%x%x%x%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%x%x%x%x%x%x%x%x$") then return nil end
  s = s:lower()
  if s == "00000000-0000-0000-0000-000000000000" then return nil end
  return s
end

function M.private_ipv4(ip)
  if type(ip) ~= "string" then return false end
  local a,b,c,d = ip:match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")
  a,b,c,d = tonumber(a),tonumber(b),tonumber(c),tonumber(d)
  if not a or a>255 or b>255 or c>255 or d>255 then return false end
  return a==10 or (a==172 and b>=16 and b<=31) or (a==192 and b==168)
end

return M
