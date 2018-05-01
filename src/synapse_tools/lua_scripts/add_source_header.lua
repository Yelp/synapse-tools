-- Loads map into Lua script
function init_add_source(txn)
  -- Load map if not yet loaded
  if map == nil then
    local map_file = txn.f:env('map_file')
    map = Map.new(map_file, Map.str)
  end
end
core.register_action('init_add_source', {'tcp-req', 'http-req'}, init_add_source)

-- Add source header to the request
function add_source_header(txn)
  -- Don't log if map doesn't exist or sampled out
  if (map == nil) then
    return
  end

  -- Get source service
  local ip = txn.f:src()
  if ip == nil then
    ip = 'nil'
  end
  
  src_svc = map:lookup(ip)
  if src_svc == nil then
    src_svc = '0'
  end

  -- Add header
  txn.http:req_add_header('X-Smartstack-Origin', src_svc)
end
core.register_action('add_source_header', {'tcp-req', 'http-req'}, add_source_header)
