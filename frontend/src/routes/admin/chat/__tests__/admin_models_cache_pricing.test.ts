import { fireEvent, render, screen, waitFor, within } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { writable } from "svelte/store";
import { t } from "$lib/i18n/ns/admin-chat";
import { t as nativeT } from '$lib/i18n/ns/native-providers';
import { t as studioT } from "$lib/i18n/ns/chat-studio";
import { initLocale } from "$lib/i18n/runtime.svelte";

const mocks = vi.hoisted(() => {
  class ApiError extends Error {
    constructor(
      message: string,
      public status: number,
    ) {
      super(message);
    }
  }
  return {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    deleteRequest: vi.fn(),
    toastError: vi.fn(),
    toastSuccess: vi.fn(),
    ApiError,
  };
});

vi.mock("$lib/stores/auth", () => ({
  auth: {
    subscribe(run: (value: { token: string; projectId: string; isSystemAdmin: boolean }) => void) {
      run({ token: "token", projectId: "project", isSystemAdmin: true });
      return () => {};
    },
  },
  authReady: writable(true),
  projectSwitching: writable(false),
}));
// Personal extension permissions are unrelated to these admin flows; do not consume API fixtures.
vi.mock("$lib/stores/servicePermissions", () => ({
  serviceCapabilities: writable<(leaf: string) => boolean>(() => false),
  projectPermissions: writable({ permissions: null, loading: false, error: "" }),
}));
vi.mock("$lib/api/client", () => ({
  api: {
    get: mocks.get,
    post: mocks.post,
    patch: mocks.patch,
    put: mocks.put,
    delete: mocks.deleteRequest,
  },
  ApiError: mocks.ApiError,
}));
vi.mock("$lib/stores/confirm.svelte", () => ({ confirmDialog: vi.fn() }));
vi.mock("$lib/stores/toast", () => ({
  toast: { success: mocks.toastSuccess, error: mocks.toastError },
}));

import { authReady, projectSwitching } from "$lib/stores/auth";
import ModelPage from "../models/+page.svelte";

const { get, post, patch, toastError } = mocks;

const CACHE_KEYS = [
  "cache_read_price_per_million",
  "cache_write_price_per_million",
  "cache_write_1h_price_per_million",
] as const;

const provider = {
  id: 1,
  name: "Anthropic",
  provider_type: "anthropic",
  api_base: null,
  has_api_key: true,
  models_dev_provider_id: "anthropic",
  is_active: true,
  margin_multiplier: 1,
};

function model(id: number, overrides: Record<string, unknown> = {}) {
  return {
    id,
    provider_id: 1,
    model_name: `anthropic/claude-${id}`,
    api_model_name: `anthropic/claude-${id}`,
    api_provider: "anthropic",
    display_name: `Claude ${id}`,
    is_active: true,
    input_price_per_million: "3",
    output_price_per_million: "15",
    effective_input_price_per_million: "3",
    effective_output_price_per_million: "15",
    effective_price_source: "manual",
    models_dev_model_id: null,
    price_source: "manual",
    // A cache-pricing Lumen always returns the three keys, null when unset.
    cache_read_price_per_million: null,
    cache_write_price_per_million: null,
    cache_write_1h_price_per_million: null,
    ...overrides,
  };
}

/** A model row from a Lumen that predates cache pricing: the keys are absent, not null. */
function legacyModel(id: number, overrides: Record<string, unknown> = {}) {
  return Object.fromEntries(
    Object.entries(model(id, overrides)).filter(([key]) => !(CACHE_KEYS as readonly string[]).includes(key)),
  );
}

function serve(models: unknown[], providerRows: unknown[] = [provider]) {
  get.mockImplementation((path: string) => {
    if (path === "/api/v1/chat/admin/providers") return Promise.resolve(providerRows);
    if (path === "/api/v1/chat/admin/models") return Promise.resolve(models);
    return Promise.resolve([]);
  });
}

function createCacheGroup(): HTMLElement {
  return document.querySelector('[data-testid="model-create-cache-prices"]') as HTMLElement;
}

async function openManualCreation(): Promise<HTMLElement> {
  const button = await screen.findByRole('button', { name: '+ 모델 추가' });
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
  await fireEvent.click(button);
  await fireEvent.click(screen.getByRole('button', { name: '직접 입력' }));
  return screen.getByRole('dialog', { name: '+ 모델 추가' });
}

async function openEditor(index = 0): Promise<HTMLElement> {
  await screen.findAllByText("가격 수정");
  await fireEvent.click(screen.getAllByText("가격 수정")[index]);
  return screen.getByText("모델 가격 수정").parentElement as HTMLElement;
}

describe("admin chat model prompt-cache pricing", () => {
  beforeEach(() => {
    initLocale("ko");
    vi.clearAllMocks();
    authReady.set(true);
    projectSwitching.set(false);
    post.mockResolvedValue({});
    patch.mockResolvedValue({});
  });

  it("lists set cache prices and distinguishes unset prices from unsupported legacy fields", async () => {
    serve([
      model(1, { cache_read_price_per_million: "0.3000000000", cache_write_price_per_million: "3.7500000000", cache_write_1h_price_per_million: "6.0000000000" }),
      model(2, { cache_read_price_per_million: "0.3" }),
      legacyModel(3),
      model(4),
    ]);
    render(ModelPage);
    await screen.findByText("Claude 4");
    const lines = Array.from(document.querySelectorAll('[data-testid="model-cache-prices"]'), (node) => node.textContent?.replace(/\s+/g, " ").trim());
    expect(lines).toEqual([
      nativeT("price.cacheSummary", { read: "0.3", write: "3.75", long: "6" }),
      nativeT("price.cacheSummary", { read: "0.3", write: t("configuration.unset"), long: t("configuration.unset") }),
      t("configuration.cacheRatesUnsupportedThisLumenVersionDoesNotAccept"),
      nativeT("price.cacheHelp"),
    ]);
  });



  it("creates a cache-only priced model without requiring text prices and resets the successful draft", async () => {
    const stored: unknown[] = [];
    serve(stored);
    post.mockImplementation(async (_path: string, changes: Record<string, unknown>) => {
      const saved = model(5, { ...changes, display_name: "Cache-only model" });
      stored.push(saved);
      return saved;
    });
    render(ModelPage);
    await openManualCreation();
    await fireEvent.input(await screen.findByPlaceholderText("모델명 (예: gpt-4o)"), {
      target: { value: "anthropic/claude-cache-only" },
    });
    await fireEvent.input(within(createCacheGroup()).getByLabelText("캐시 읽기"), { target: { value: " 0.3 " } });
    await fireEvent.click(within(screen.getByRole('dialog', { name: '+ 모델 추가' })).getByRole('button', { name: '+ 모델 추가' }));
    await screen.findByRole("checkbox", { name: "Cache-only model 선택" });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '+ 모델 추가' })).toBeNull());
    const cleanDraft = await openManualCreation();
    expect((within(createCacheGroup()).getByLabelText("캐시 읽기") as HTMLInputElement).value).toBe("");
    await fireEvent.click(within(cleanDraft).getAllByRole('button', { name: '닫기' }).at(-1)!);
    const editor = await openEditor();
    expect((within(editor).getByLabelText("캐시 읽기") as HTMLInputElement).value).toBe("0.3");
    expect((within(editor).getByLabelText(nativeT("price.cacheWrite")) as HTMLInputElement).value).toBe("");
    expect((within(editor).getByLabelText(nativeT("price.cacheWriteLong")) as HTMLInputElement).value).toBe("");
    expect((within(editor).getByLabelText("입력") as HTMLInputElement).value).toBe("");
    expect((within(editor).getByLabelText("출력") as HTMLInputElement).value).toBe("");
    expect(toastError).not.toHaveBeenCalled();
  });

  it("omits every cache key on create when all cache prices are blank", async () => {
    serve([]);
    render(ModelPage);
    await openManualCreation();
    await fireEvent.input(await screen.findByPlaceholderText("모델명 (예: gpt-4o)"), {
      target: { value: "anthropic/claude-plain" },
    });
    await fireEvent.input(screen.getByPlaceholderText("입력 가격 (USD / 1M tokens)"), { target: { value: "3" } });
    await fireEvent.input(screen.getByPlaceholderText("출력 가격 (USD / 1M tokens)"), { target: { value: "15" } });
    await fireEvent.click(within(screen.getByRole('dialog', { name: '+ 모델 추가' })).getByRole('button', { name: '+ 모델 추가' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const body = post.mock.calls[0][1];
    for (const key of CACHE_KEYS) expect(body).not.toHaveProperty(key);
    expect(body).toMatchObject({ input_price_per_million: "3", output_price_per_million: "15" });
  });

  it("rejects invalid cache prices in the field before submitting and clears the error once corrected", async () => {
    serve([]);
    render(ModelPage);
    await openManualCreation();
    await fireEvent.input(await screen.findByPlaceholderText("모델명 (예: gpt-4o)"), {
      target: { value: "anthropic/claude-bad" },
    });
    const group = createCacheGroup();
    const write5m = within(group).getByLabelText(nativeT("price.cacheWrite")) as HTMLInputElement;
    const write1h = within(group).getByLabelText(nativeT("price.cacheWriteLong")) as HTMLInputElement;
    await fireEvent.input(write5m, { target: { value: "-1" } });
    await fireEvent.input(write1h, { target: { value: "1e3" } });
    await fireEvent.click(within(screen.getByRole('dialog', { name: '+ 모델 추가' })).getByRole('button', { name: '+ 모델 추가' }));

    expect(write5m.getAttribute("aria-invalid")).toBe("true");
    expect(write5m.getAttribute("aria-describedby")).toBe("model-create-cache-write-5m-message");
    expect(post).not.toHaveBeenCalled();

    await fireEvent.input(write5m, { target: { value: "3.75" } });
    expect(write5m.getAttribute("aria-invalid")).toBeNull();

    for (const bad of ["Infinity", "NaN", "0x10", "1,5"]) {
      await fireEvent.input(write1h, { target: { value: bad } });
      await fireEvent.click(within(screen.getByRole('dialog', { name: '+ 모델 추가' })).getByRole('button', { name: '+ 모델 추가' }));
      expect(post).not.toHaveBeenCalled();
    }
  });


  it("renders a scientific-notation zero cache price from Lumen as 0 in the list", async () => {
    serve([
      model(1, { cache_read_price_per_million: "0E-10", cache_write_price_per_million: "3.7500000000", cache_write_1h_price_per_million: "6.0000000000" }),
      model(2, { cache_read_price_per_million: "0.0000000000" }),
    ]);
    render(ModelPage);
    await screen.findByText("Claude 2");
    const lines = Array.from(document.querySelectorAll('[data-testid="model-cache-prices"]'), (node) => node.textContent?.replace(/\s+/g, " ").trim());
    expect(lines).toEqual([
      nativeT("price.cacheSummary", { read: "0", write: "3.75", long: "6" }),
      nativeT("price.cacheSummary", { read: "0", write: t("configuration.unset"), long: t("configuration.unset") }),
    ]);
    expect(document.body.textContent).not.toContain("0E-10");
  });

  it("prefills a scientific-notation zero as 0 and still saves an unrelated output change", async () => {
    const stored = model(1, { cache_read_price_per_million: "0E-10" });
    serve([stored]);
    patch.mockImplementation(async (_path: string, changes: Record<string, unknown>) => Object.assign(stored, changes));
    render(ModelPage);
    const modal = await openEditor();
    expect((within(modal).getByLabelText("캐시 읽기") as HTMLInputElement).value).toBe("0");

    await fireEvent.input(within(modal).getByLabelText("출력"), { target: { value: "16" } });
    await fireEvent.click(within(modal).getByText("저장"));

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    expect(patch.mock.calls[0][1]).toStrictEqual({ output_price_per_million: "16" });
    await waitFor(() => expect(screen.queryByText("모델 가격 수정")).toBeNull());
    const reopened = await openEditor();
    expect((within(reopened).getByLabelText("입력") as HTMLInputElement).value).toBe("3");
    expect((within(reopened).getByLabelText("출력") as HTMLInputElement).value).toBe("16");
    expect((within(reopened).getByLabelText("캐시 읽기") as HTMLInputElement).value).toBe("0");
    expect(within(reopened).queryByText(t("configuration.enterANumberGreaterThanOrEqualTo0"))).toBeNull();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("sends only the changed cache key for a models.dev-priced model so it is not flipped to manual", async () => {
    // Storage-precision strings: comparing against formatted values would wrongly see a change.
    serve([
      model(1, {
        input_price_per_million: "3.0000000000",
        output_price_per_million: "15.0000000000",
        effective_input_price_per_million: "3.0000000000",
        effective_output_price_per_million: "15.0000000000",
        effective_price_source: "models.dev",
        models_dev_model_id: "anthropic/claude-1",
        price_source: "models.dev",
      }),
    ]);
    render(ModelPage);
    const modal = await openEditor();
    await fireEvent.input(within(modal).getByLabelText("캐시 읽기"), { target: { value: "0.3" } });
    await fireEvent.click(within(modal).getByText("저장"));

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    const [path, body] = patch.mock.calls[0];
    expect(path).toBe("/api/v1/chat/admin/models/1");
    expect(body).toStrictEqual({ cache_read_price_per_million: "0.3" });
    expect(body).not.toHaveProperty("input_price_per_million");
    expect(body).not.toHaveProperty("output_price_per_million");
  });

  it("closes the editor without a PATCH when nothing changed", async () => {
    serve([model(1, { cache_read_price_per_million: "0.3000000000" })]);
    render(ModelPage);
    const modal = await openEditor();
    await fireEvent.click(within(modal).getByText("저장"));

    await waitFor(() => expect(screen.queryByText("모델 가격 수정")).toBeNull());
    expect(patch).not.toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  });

  it("patches only changed cache keys, clearing a blanked one with null, without the input/output pair rule", async () => {
    serve([
      model(1, {
        input_price_per_million: null,
        output_price_per_million: null,
        price_source: null,
        effective_price_source: "litellm",
        cache_read_price_per_million: "0.3",
        // Storage-precision strings prefill without trailing zeros (same decimal value).
        cache_write_price_per_million: "3.7500000000",
        cache_write_1h_price_per_million: null,
      }),
    ]);
    render(ModelPage);
    const modal = await openEditor();
    const read = within(modal).getByLabelText("캐시 읽기") as HTMLInputElement;
    expect(read.value).toBe("0.3");
    expect((within(modal).getByLabelText(nativeT("price.cacheWrite")) as HTMLInputElement).value).toBe("3.75");
    expect((within(modal).getByLabelText(nativeT("price.cacheWriteLong")) as HTMLInputElement).value).toBe("");

    await fireEvent.input(read, { target: { value: "" } });
    await fireEvent.input(within(modal).getByLabelText(nativeT("price.cacheWriteLong")), { target: { value: "6" } });
    await fireEvent.click(within(modal).getByText("저장"));

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    const [path, body] = patch.mock.calls[0];
    expect(path).toBe("/api/v1/chat/admin/models/1");
    // The untouched 5-minute write price and the untouched (blank) input/output pair stay absent.
    expect(body).toStrictEqual({
      cache_read_price_per_million: null,
      cache_write_1h_price_per_million: "6",
    });
    expect(toastError).not.toHaveBeenCalled();
  });

  it("hides cache inputs and sends no cache keys when an older Lumen omitted them from the model", async () => {
    serve([legacyModel(1)]);
    render(ModelPage);
    await screen.findByText("Claude 1");
    expect(screen.queryByText(t("configuration.cacheRatesUnsetCacheTokensAreBilledAt0"))).toBeNull();
    // Every loaded row is from the older Lumen, so the create form offers no cache inputs either.
    const creation = await openManualCreation();
    expect(createCacheGroup()).toBeNull();
    await fireEvent.click(within(creation).getAllByRole('button', { name: '닫기' }).at(-1)!);
    const modal = await openEditor();
    for (const label of ["캐시 읽기", nativeT("price.cacheWrite"), nativeT("price.cacheWriteLong")]) {
      expect(within(modal).queryByLabelText(label)).toBeNull();
    }
    await fireEvent.input(within(modal).getByLabelText("출력"), { target: { value: "16" } });
    await fireEvent.click(within(modal).getByText("저장"));

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    const body = patch.mock.calls[0][1];
    expect(body).toStrictEqual({
      output_price_per_million: "16",
    });
    for (const key of CACHE_KEYS) expect(body).not.toHaveProperty(key);
  });

  it("keeps the create form cache inputs while any loaded model supports cache pricing", async () => {
    serve([legacyModel(1), model(2)]);
    render(ModelPage);
    await screen.findByText("Claude 2");
    await openManualCreation();
    expect(createCacheGroup()).not.toBeNull();
  });

  it("clears only the output price while preserving free input and cache prices on reopen", async () => {
    const stored = model(1, { input_price_per_million: "0", cache_read_price_per_million: "0.3" });
    serve([stored]);
    patch.mockImplementation(async (_path: string, changes: Record<string, unknown>) => Object.assign(stored, changes));
    render(ModelPage);
    const modal = await openEditor();
    await fireEvent.input(within(modal).getByLabelText("출력"), { target: { value: "" } });
    await fireEvent.click(within(modal).getByText("저장"));

    await waitFor(() => expect(screen.queryByText("모델 가격 수정")).toBeNull());
    const reopened = await openEditor();
    expect((within(reopened).getByLabelText("입력") as HTMLInputElement).value).toBe("0");
    expect((within(reopened).getByLabelText("출력") as HTMLInputElement).value).toBe("");
    expect((within(reopened).getByLabelText("캐시 읽기") as HTMLInputElement).value).toBe("0.3");
    expect(patch).toHaveBeenCalledWith("/api/v1/chat/admin/models/1", { output_price_per_million: null }, "token", "project");
    expect(toastError).not.toHaveBeenCalled();
  });

  it("blocks saving an invalid cache price in the editor and clears stale errors on reopen", async () => {
    serve([model(1)]);
    render(ModelPage);
    let modal = await openEditor();
    await fireEvent.input(within(modal).getByLabelText("캐시 읽기"), { target: { value: "-0.1" } });
    await fireEvent.click(within(modal).getByText("저장"));
    expect(within(modal).getByLabelText("캐시 읽기").getAttribute("aria-invalid")).toBe("true");
    expect(patch).not.toHaveBeenCalled();

    await fireEvent.click(within(modal).getByText("취소"));
    modal = await openEditor();
    expect(within(modal).getByLabelText("캐시 읽기").getAttribute("aria-invalid")).toBeNull();
    expect((within(modal).getByLabelText("캐시 읽기") as HTMLInputElement).value).toBe("");
  });
});

describe("admin media model registration", () => {
  const openai = { ...provider, id: 2, name: "OpenAI", provider_type: "openai", auth_mode: "api_key", api_base: null };

  beforeEach(() => {
    vi.clearAllMocks();
    post.mockResolvedValue({});
    patch.mockResolvedValue({});
  });

  it("registers an image variant as a unit price without leaking token/cache fields", async () => {
    serve([], [openai]);
    render(ModelPage);
    await screen.findByText("모델");
    await openManualCreation();
    await fireEvent.change(screen.getByLabelText("모델 종류"), { target: { value: "image" } });
    await fireEvent.input(screen.getByPlaceholderText("모델명 (예: gpt-4o)"), { target: { value: "gpt-image-1" } });
    await fireEvent.click(screen.getByText("+ variant 추가"));
    await fireEvent.input(screen.getByLabelText("이미지 variant 이름"), { target: { value: "1024x1024:high" } });
    await fireEvent.input(screen.getByLabelText("이미지 variant 단가"), { target: { value: "0.08" } });
    await fireEvent.click(within(screen.getByRole('dialog', { name: '+ 모델 추가' })).getByRole('button', { name: '+ 모델 추가' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(JSON.parse(JSON.stringify(post.mock.calls[0][1]))).toStrictEqual({
      provider_id: 2,
      model_name: "gpt-image-1",
      display_name: null,
      model_kind: "image",
      media_pricing: { override_mode: "leaf", image_variants: { "1024x1024:high": "0.08" } },
    });
  });

  it("shows unexecutable readiness and updates only changed media prices", async () => {
    serve([model(1, {
      provider_id: 2,
      model_name: "gpt-image-1",
      api_model_name: "gpt-image-1",
      display_name: "Image Maker",
      model_kind: "image",
      input_price_per_million: null,
      output_price_per_million: null,
      media_pricing: { image_variants: { "1024x1024:high": "0.08" } },
      effective_capabilities: { feature_gates: { image_output: { available: false, mode: "none", reason_code: "route_unavailable", pricing_available: true } } },
    })], [openai]);
    render(ModelPage);
    await screen.findByText("Image Maker");
    expect(screen.getByText(studioT("mediaReadiness.route"))).toBeTruthy();
    expect(screen.queryByText("실행 경로 없음 · 실행 불가")).toBeNull();
    expect(screen.getByText(/1024x1024:high: 0.08 USD \/ 장/)).toBeTruthy();
    const modal = await openEditor();
    await fireEvent.input(within(modal).getByLabelText("이미지 variant 단가"), { target: { value: "0.12" } });
    await fireEvent.click(within(modal).getByText("저장"));
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    expect(JSON.parse(JSON.stringify(patch.mock.calls[0][1]))).toStrictEqual({ media_pricing: { image_variants: { "1024x1024:high": "0.12" } } });
  });

  it("shows the asset-pipeline operator reason and a ready success state for media rows", async () => {
    const gate = (reason_code: string | null, available: boolean) => ({ feature_gates: { image_output: { available, mode: available ? "native" : "none", reason_code, pricing_available: true } } });
    serve([
      model(1, { provider_id: 2, display_name: "Blocked Image", model_kind: "image", media_pricing: { image_variants: { "1024x1024:low": "0.02" } }, effective_capabilities: gate("asset_pipeline_unavailable", false) }),
      model(2, { provider_id: 2, display_name: "Ready Image", model_kind: "image", media_pricing: { image_variants: { "1024x1024:low": "0.02" } }, effective_capabilities: gate(null, true) }),
    ], [openai]);
    render(ModelPage);
    await screen.findByText("Blocked Image");
    expect(screen.getByText(studioT("mediaReadiness.assets"))).toBeTruthy();
    expect(screen.getByText(studioT("mediaReadiness.ready"))).toBeTruthy();
    expect(document.body.textContent).not.toContain("asset_pipeline_unavailable");
  });

  async function reviewDiscovered(candidates: Record<string, unknown>[]) {
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([openai]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path === "/api/v1/chat/admin/providers/2/available-models") return Promise.resolve({ provider_id: 2, source: "api", live_status: "success", complete: true, fetched_at: "2026-11-17T00:00:00Z", models: candidates.map((c) => c.id), candidates });
      return Promise.resolve([]);
    });
    render(ModelPage);
    const add = await screen.findByRole("button", { name: "+ 모델 추가" });
    await waitFor(() => expect((add as HTMLButtonElement).disabled).toBe(false));
    await fireEvent.click(add);
    await fireEvent.click(await screen.findByRole("button", { name: "모델 불러오기" }));
    for (const candidate of candidates) await fireEvent.click(await screen.findByLabelText(String(candidate.id)));
    await fireEvent.click(screen.getByRole("button", { name: "선택 모델 검토" }));
  }

  it("preselects embedding from discovery and registers it with input-token price only", async () => {
    await reviewDiscovered([{ id: "text-embedding-3-small", model_kind: "embedding", purpose: "non_chat", input_token_limit: 8191 }]);
    const kind = document.querySelector("#review-kind-0") as HTMLSelectElement;
    expect(kind.value).toBe("embedding");
    expect([...kind.options].map((option) => option.value)).toContain("embedding");
    expect(document.querySelector("#review-output-0")).toBeNull();
    await fireEvent.input(document.querySelector("#review-input-0")!, { target: { value: "0.02" } });
    await fireEvent.click(screen.getByRole("button", { name: "비활성으로 저장" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(JSON.parse(JSON.stringify(post.mock.calls[0][1]))).toStrictEqual({ provider_id: 2, model_name: "text-embedding-3-small", model_kind: "embedding", input_price_per_million: "0.02", is_active: false });
  });

  it("requires an explicit kind for a Lumen kind this build does not know and never prints a raw placeholder", async () => {
    await reviewDiscovered([{ id: "future-model", model_kind: "video", purpose: "non_chat" }]);
    const kind = document.querySelector("#review-kind-0") as HTMLSelectElement;
    expect(kind.value).toBe("");
    expect(await screen.findByText(t("pricing.kindRequired"))).toBeTruthy();
    expect((screen.getByRole("button", { name: "비활성으로 저장" }) as HTMLButtonElement).disabled).toBe(true);
    expect(document.body.textContent).not.toMatch(/\{\w+\}/);
    expect(post).not.toHaveBeenCalled();
  });

  it.each(["gpt-image-2", "gpt-image-2.5-flare"])("lets %s choose OpenAI token billing without a fixed reservation", async (name) => {
    const media = { token_rates: { image: { input_per_million: "8", cache_read_per_million: "2", output_per_million: "30" } } };
    serve([model(1, { provider_id: 2, model_name: name, display_name: name, model_kind: "image",
      input_price_per_million: "5", effective_input_price_per_million: "5",
      output_price_per_million: null, effective_output_price_per_million: null, media_pricing: media })], [openai]);
    render(ModelPage);
    const modal = await openEditor();
    expect((within(modal).getByRole("radio", { name: t("pricing.imageUnit") }) as HTMLInputElement).checked).toBe(true);
    expect(document.querySelector("#model-edit-reservation-usd")).toBeNull();
    await fireEvent.click(within(modal).getByRole("radio", { name: t("pricing.imageTokenUnit") }));
    const reservation = within(modal).getByLabelText(t("pricing.reservationCap")) as HTMLInputElement;
    expect(reservation.value).toBe("");
    expect(within(modal).getByText(t("pricing.imageDerivedReservation"))).toBeTruthy();
    await fireEvent.click(within(modal).getByText("저장"));
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    expect(toastError).not.toHaveBeenCalled();
    expect(JSON.parse(JSON.stringify(patch.mock.calls[0][1]))).toStrictEqual({
      media_pricing: { ...media, billing_basis: "tokens" },
    });
  });

  it.each(["gpt-realtime-whisper", "gpt-live-transcribe"])("saves explicit input-only realtime duration pricing for %s", async (name) => {
    serve([model(1, { provider_id: 2, model_name: name, display_name: name, model_kind: "realtime",
      input_price_per_million: null, effective_input_price_per_million: null,
      output_price_per_million: null, effective_output_price_per_million: null, media_pricing: null })], [openai]);
    render(ModelPage);
    const modal = await openEditor();
    await fireEvent.change(within(modal).getByLabelText(t("pricing.billingBasis", { kind: t("configuration.realtimeAudio") })), { target: { value: "duration" } });
    const input = document.querySelector("#model-edit-realtime_input_per_minute") as HTMLInputElement;
    const output = document.querySelector("#model-edit-realtime_output_per_minute") as HTMLInputElement;
    expect(input.value).toBe("");
    expect(output.value).toBe("");
    await fireEvent.input(input, { target: { value: "0.017" } });
    await fireEvent.click(within(modal).getByText("저장"));
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    expect(JSON.parse(JSON.stringify(patch.mock.calls[0][1]))).toStrictEqual({
      media_pricing: { billing_basis: "duration", realtime_input_per_minute: "0.017" },
    });
  });
});
