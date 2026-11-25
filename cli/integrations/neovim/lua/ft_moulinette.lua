local M = {}
function M.setup(opts)
  opts = opts or {}
  local executable = opts.executable or 'ft-moulinette'
  vim.api.nvim_create_user_command('Moulinette', function(cmd)
    vim.cmd('wall')
    local target = cmd.args ~= '' and vim.fn.fnamemodify(cmd.args, ':p') or vim.fn.getcwd()
    vim.system({ executable, target, '--json' }, { text = true }, function(result)
      vim.schedule(function()
        local ok, report = pcall(vim.json.decode, result.stdout or '')
        if not ok then vim.notify(result.stderr or 'Rapport invalide', vim.log.levels.ERROR); return end
        local items = {}
        for _, row in ipairs(report.results) do
          if row.status ~= 'pass' and row.status ~= 'skip' and row.status ~= 'manual' and row.status ~= 'reviewed' then
            for _, detail in ipairs(row.diagnostics or { row }) do
              table.insert(items, { filename = detail.file, lnum = detail.line, col = detail.column or 1, text = row.status .. ' [' .. row.check .. '] ' .. detail.message, type = row.status == 'fail' and 'E' or 'W' })
            end
          end
        end
        vim.fn.setqflist({}, 'r', { title = 'Libft Moulinette', items = items })
        vim.cmd('copen')
      end)
    end)
  end, { nargs = '?', complete = 'file' })
  vim.api.nvim_create_user_command('MoulinetteFile', function()
    vim.cmd('Moulinette ' .. vim.fn.fnameescape(vim.api.nvim_buf_get_name(0)))
  end, {})
end
return M
