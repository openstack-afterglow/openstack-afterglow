// Vitest $app/state fixture; individual consumer tests override it with vi.mock().
export const page = { data: {}, url: new URL('http://localhost/'), state: {} as App.PageState };
