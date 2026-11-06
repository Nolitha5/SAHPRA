import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from './api'

function respond(status: number, body: string) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(body, { status })))
}

afterEach(() => { vi.unstubAllGlobals() })

describe('api client', () => {
  it('returns the parsed body on success', async () => {
    respond(200, JSON.stringify({ status: 'ok', knowledge_base_size: 3 }))
    await expect(api.health()).resolves.toMatchObject({ knowledge_base_size: 3 })
  })

  it('turns FastAPI validation errors into readable text without the "body" prefix', async () => {
    respond(422, JSON.stringify({ detail: [{ loc: ['body', 'query'], msg: 'String should have at most 2000 characters' }] }))
    await expect(api.search('x', {})).rejects.toMatchObject({
      status: 422, message: 'query: String should have at most 2000 characters',
    })
  })

  it('passes plain-string details through', async () => {
    respond(401, JSON.stringify({ detail: 'Editor token is missing or wrong.' }))
    await expect(api.deletePassage('c1')).rejects.toThrow('Editor token is missing or wrong.')
  })

  it('explains a non-JSON server error instead of crashing', async () => {
    respond(502, '<html>Bad Gateway</html>')
    const err = await api.health().catch(e => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(502)
    expect(err.message).toMatch(/not responding/)
  })

  it('reports an unreachable server', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    await expect(api.health()).rejects.toMatchObject({ status: 0, message: expect.stringMatching(/Cannot reach/) })
  })

  it('sends the editor token header only on editing calls', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await api.health()
    await api.deleteCase('Q1')
    const headers = (call: number) => (fetchMock.mock.calls[call] as unknown as [string, RequestInit])[1].headers as Record<string, string>
    expect(headers(0)).not.toHaveProperty('X-Admin-Token')
    expect(headers(1)).toHaveProperty('X-Admin-Token')
  })
})
