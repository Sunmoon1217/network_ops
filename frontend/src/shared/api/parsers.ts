import api from './index'

export const getParsers = () =>
  api.get('/api/parsers/').then((r) => r.data)

export const getParserTemplates = () =>
  api.get('/api/parsers/templates/').then((r) => r.data)

export const getParserTemplate = (name: string) =>
  api.get(`/api/parsers/templates/${name}/`).then((r) => r.data)

export const updateParserTemplate = (name: string, content: string) =>
  api.put(`/api/parsers/templates/${name}/update/`, { content }).then((r) => r.data)
