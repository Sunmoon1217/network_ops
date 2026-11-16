import api from './index'

export const getParsers = () =>
  api.get('/api/ingest/parsers/').then((r) => r.data)

export const getParserTemplates = () =>
  api.get('/api/ingest/parsers/templates/').then((r) => r.data)

export const getParserTemplate = (name: string) =>
  api.get(`/api/ingest/parsers/templates/${name}/`).then((r) => r.data)

export const updateParserTemplate = (name: string, content: string) =>
  api.put(`/api/ingest/parsers/templates/${name}/update/`, { content }).then((r) => r.data)
