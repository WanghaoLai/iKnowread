import contract from './apiContract.json' with { type: 'json' }

const parameterPattern = /\{([a-z_]+)\}/g

const pathParameter = (name, value) => {
  const normalized = Number(value)
  if (!Number.isSafeInteger(normalized) || normalized < 1) {
    throw new TypeError(`${name} must be a positive integer`)
  }
  return String(normalized)
}

export const apiContract = Object.freeze(contract)

export const apiPath = (name, parameters = {}) => {
  const template = contract[name]?.path
  if (!template) throw new TypeError(`unknown API endpoint: ${name}`)
  return template.replace(parameterPattern, (_, parameter) => (
    pathParameter(parameter, parameters[parameter])
  ))
}

export const apiMethod = name => {
  const method = contract[name]?.method
  if (!method) throw new TypeError(`unknown API endpoint: ${name}`)
  return method
}
