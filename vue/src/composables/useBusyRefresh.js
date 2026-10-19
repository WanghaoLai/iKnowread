// 列表存在"处理中"行时按固定间隔自动重载：每次调度先清掉旧定时器，
// 仅当 isBusy() 为真时才排下一次刷新，避免空转轮询。
export function useBusyRefresh(reload, isBusy, { interval = 3000 } = {}) {
  let timer = null

  function schedule() {
    clearTimeout(timer)
    if (isBusy()) timer = setTimeout(reload, interval)
  }

  function stop() {
    clearTimeout(timer)
  }

  return { schedule, stop }
}
