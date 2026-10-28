import assert from 'node:assert/strict'
import test from 'node:test'

import { useListLoader } from '../src/composables/useListLoader.js'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((accept, decline) => {
    resolve = accept
    reject = decline
  })
  return { promise, resolve, reject }
}

test('stale list failures stay silent and cannot release the latest loading state', async () => {
  const requests = []
  const errors = []
  const loader = useListLoader((options, name) => {
    const pending = deferred()
    requests.push({ name, options, pending })
    return pending.promise
  }, {
    cancellable: true,
    onError: error => errors.push(error.message),
  })

  const oldLoad = loader.load('old')
  const newLoad = loader.load('new')
  assert.equal(requests[0].options.skipErrorToast, true)
  assert.equal(requests[0].options.signal.aborted, true)
  assert.equal(requests[1].options.signal.aborted, false)

  requests[0].pending.reject(new Error('old failure'))
  assert.equal(await oldLoad, null)
  assert.deepEqual(errors, [])
  assert.equal(loader.loading.value, true)

  requests[1].pending.resolve({ data: 'latest' })
  assert.deepEqual(await newLoad, { data: 'latest' })
  assert.equal(loader.loading.value, false)
})

test('only the current non-cancelled failure is reported', async () => {
  const errors = []
  const loader = useListLoader(async options => {
    assert.equal(options.skipErrorToast, true)
    throw new Error('current failure')
  }, { onError: error => errors.push(error.message) })

  assert.equal(await loader.load(), null)
  assert.deepEqual(errors, ['current failure'])
})

test('a cancelled current request never produces an error notification', async () => {
  const errors = []
  const loader = useListLoader(async () => {
    const error = new Error('cancelled')
    error.code = 'ERR_CANCELED'
    throw error
  }, { onError: error => errors.push(error.message) })

  assert.equal(await loader.load(), null)
  assert.deepEqual(errors, [])
  assert.equal(loader.loading.value, false)
})
