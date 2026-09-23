import { fireEvent, render, screen, waitFor, within } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

import ModelPage from "../models/+page.svelte";

const { get, post, patch, toastError } = mocks;

const CACHE_KEYS = [
  "cache_read_price_per_million",
  "cache_write_price_per_million",
  "cache_write_1h_price_per_million",
] as const;
const PAIR_RULE_MESSAGE = "입력·출력 가격은 함께 입력하거나 함께 비워야 합니다";
const CACHE_PRICE_ERROR = "0 이상의 숫자로 입력하세요 (예: 0.3)";
const UNSET_NOTE = "캐시 단가 미설정 · 캐시 토큰은 단가를 설정할 때까지 0 USD로 청구됩니다";
const UNSUPPORTED_NOTE = "캐시 단가 미지원 · 이 Lumen 버전은 캐시 단가를 받지 않습니다";

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

function serve(models: unknown[]) {
  get.mockImplementation((path: string) => {
    if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider]);
    if (path === "/api/v1/chat/admin/models") return Promise.resolve(models);
    return Promise.resolve([]);
  });
}

function createCacheGroup(): HTMLElement {
  return document.querySelector('[data-testid="model-create-cache-prices"]') as HTMLElement;
}

async function openEditor(index = 0): Promise<HTMLElement> {
  await screen.findAllByText("가격 수정");
  await fireEvent.click(screen.getAllByText("가격 수정")[index]);
  return screen.getByText("모델 가격 수정").parentElement as HTMLElement;
}

describe("admin chat model prompt-cache pricing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    post.mockResolvedValue({});
    patch.mockResolvedValue({});
  });

  it("lists set cache prices and marks unset components as billed at 0 USD", async () => {
    serve([
      model(1, {
        cache_read_price_per_million: "0.3000000000",
        cache_write_price_per_million: "3.7500000000",
        cache_write_1h_price_per_million: "6.0000000000",
      }),
      model(2, { cache_read_price_per_million: "0.3" }),
      legacyModel(3),
      model(4, {
        cache_read_price_per_million: null,
        cache_write_price_per_million: null,
        cache_write_1h_price_per_million: null,
      }),
    ]);
    render(ModelPage);
    await screen.findByText("Claude 4");

    const lines = Array.from(document.querySelectorAll('[data-testid="model-cache-prices"]')).map((node) =>
      node.textContent?.replace(/\s+/g, " ").trim(),
    );
    expect(lines).toEqual([
      "캐시 읽기 0.3 · 캐시 쓰기 5분 3.75 · 캐시 쓰기 1시간 6 USD / 1M tokens",
      "캐시 읽기 0.3 · 캐시 쓰기 5분 미설정 · 캐시 쓰기 1시간 미설정 USD / 1M tokens · 미설정 항목은 0 USD로 청구",
      // An older Lumen omits the fields: it neither prices cache nor accepts the keys, so the
      // row must not claim a 0 USD cache bill. Explicit nulls are a cleared, 0 USD price.
      UNSUPPORTED_NOTE,
      UNSET_NOTE,
    ]);
    expect(screen.getAllByText(UNSET_NOTE)).toHaveLength(1);
  });

  it("creates a model with only a cache read price, omitting blank cache keys and skipping the pair rule", async () => {
    serve([]);
    render(ModelPage);
    await fireEvent.input(await screen.findByPlaceholderText("모델명 (예: gpt-4o)"), {
      target: { value: "anthropic/claude-new" },
    });
    await fireEvent.input(within(createCacheGroup()).getByLabelText("캐시 읽기"), { target: { value: " 0.3 " } });
    await fireEvent.click(screen.getByText("+ 모델 추가"));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [path, body] = post.mock.calls[0];
    expect(path).toBe("/api/v1/chat/admin/models");
    expect(body).toStrictEqual({
      provider_id: 1,
      model_name: "anthropic/claude-new",
      display_name: null,
      input_price_per_million: null,
      output_price_per_million: null,
      cache_read_price_per_million: "0.3",
    });
    expect(body).not.toHaveProperty("cache_write_price_per_million");
    expect(body).not.toHaveProperty("cache_write_1h_price_per_million");
    expect(toastError).not.toHaveBeenCalled();
    // The form resets after a successful create.
    await waitFor(() =>
      expect((within(createCacheGroup()).getByLabelText("캐시 읽기") as HTMLInputElement).value).toBe(""),
    );
  });

  it("omits every cache key on create when all cache prices are blank", async () => {
    serve([]);
    render(ModelPage);
    await fireEvent.input(await screen.findByPlaceholderText("모델명 (예: gpt-4o)"), {
      target: { value: "anthropic/claude-plain" },
    });
    await fireEvent.input(screen.getByPlaceholderText("입력 가격 (USD / 1M tokens)"), { target: { value: "3" } });
    await fireEvent.input(screen.getByPlaceholderText("출력 가격 (USD / 1M tokens)"), { target: { value: "15" } });
    await fireEvent.click(screen.getByText("+ 모델 추가"));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const body = post.mock.calls[0][1];
    for (const key of CACHE_KEYS) expect(body).not.toHaveProperty(key);
    expect(body).toMatchObject({ input_price_per_million: "3", output_price_per_million: "15" });
  });

  it("rejects invalid cache prices in the field before submitting and clears the error once corrected", async () => {
    serve([]);
    render(ModelPage);
    await fireEvent.input(await screen.findByPlaceholderText("모델명 (예: gpt-4o)"), {
      target: { value: "anthropic/claude-bad" },
    });
    const group = createCacheGroup();
    const write5m = within(group).getByLabelText("캐시 쓰기 5분") as HTMLInputElement;
    const write1h = within(group).getByLabelText("캐시 쓰기 1시간") as HTMLInputElement;
    await fireEvent.input(write5m, { target: { value: "-1" } });
    await fireEvent.input(write1h, { target: { value: "1e3" } });
    await fireEvent.click(screen.getByText("+ 모델 추가"));

    expect(await within(group).findAllByText(CACHE_PRICE_ERROR)).toHaveLength(2);
    expect(write5m.getAttribute("aria-invalid")).toBe("true");
    expect(write5m.getAttribute("aria-describedby")).toBe("model-create-cache-write-5m-message");
    expect(post).not.toHaveBeenCalled();

    await fireEvent.input(write5m, { target: { value: "3.75" } });
    expect(within(group).getAllByText(CACHE_PRICE_ERROR)).toHaveLength(1);
    expect(write5m.getAttribute("aria-invalid")).toBeNull();

    for (const bad of ["Infinity", "NaN", "0x10", "1,5"]) {
      await fireEvent.input(write1h, { target: { value: bad } });
      await fireEvent.click(screen.getByText("+ 모델 추가"));
      expect(post).not.toHaveBeenCalled();
    }
  });

  it("renders a scientific-notation zero cache price from Lumen as 0 in the list", async () => {
    // Lumen serializes a stored Decimal zero as "0E-10"; nonzero values stay plain.
    serve([
      model(1, {
        cache_read_price_per_million: "0E-10",
        cache_write_price_per_million: "3.7500000000",
        cache_write_1h_price_per_million: "6.0000000000",
      }),
      model(2, { cache_read_price_per_million: "0.0000000000" }),
    ]);
    render(ModelPage);
    await screen.findByText("Claude 2");

    const lines = Array.from(document.querySelectorAll('[data-testid="model-cache-prices"]')).map((node) =>
      node.textContent?.replace(/\s+/g, " ").trim(),
    );
    expect(lines).toEqual([
      "캐시 읽기 0 · 캐시 쓰기 5분 3.75 · 캐시 쓰기 1시간 6 USD / 1M tokens",
      "캐시 읽기 0 · 캐시 쓰기 5분 미설정 · 캐시 쓰기 1시간 미설정 USD / 1M tokens · 미설정 항목은 0 USD로 청구",
    ]);
    expect(document.body.textContent).not.toContain("0E-10");
  });

  it("prefills a scientific-notation zero as 0 and still saves an unrelated output change", async () => {
    serve([model(1, { cache_read_price_per_million: "0E-10" })]);
    render(ModelPage);
    const modal = await openEditor();
    expect((within(modal).getByLabelText("캐시 읽기") as HTMLInputElement).value).toBe("0");

    await fireEvent.input(within(modal).getByLabelText("출력"), { target: { value: "16" } });
    await fireEvent.click(within(modal).getByText("저장"));

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    expect(patch.mock.calls[0][1]).toStrictEqual({
      input_price_per_million: "3",
      output_price_per_million: "16",
    });
    expect(within(modal).queryByText(CACHE_PRICE_ERROR)).toBeNull();
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
    expect((within(modal).getByLabelText("캐시 쓰기 5분") as HTMLInputElement).value).toBe("3.75");
    expect((within(modal).getByLabelText("캐시 쓰기 1시간") as HTMLInputElement).value).toBe("");

    await fireEvent.input(read, { target: { value: "" } });
    await fireEvent.input(within(modal).getByLabelText("캐시 쓰기 1시간"), { target: { value: "6" } });
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
    await screen.findByText(UNSUPPORTED_NOTE);
    expect(screen.queryByText(UNSET_NOTE)).toBeNull();
    // Every loaded row is from the older Lumen, so the create form offers no cache inputs either.
    expect(createCacheGroup()).toBeNull();
    const modal = await openEditor();
    for (const label of ["캐시 읽기", "캐시 쓰기 5분", "캐시 쓰기 1시간"]) {
      expect(within(modal).queryByLabelText(label)).toBeNull();
    }
    await fireEvent.input(within(modal).getByLabelText("출력"), { target: { value: "16" } });
    await fireEvent.click(within(modal).getByText("저장"));

    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    const body = patch.mock.calls[0][1];
    expect(body).toStrictEqual({
      input_price_per_million: "3",
      output_price_per_million: "16",
    });
    for (const key of CACHE_KEYS) expect(body).not.toHaveProperty(key);
  });

  it("keeps the create form cache inputs while any loaded model supports cache pricing", async () => {
    serve([legacyModel(1), model(2)]);
    render(ModelPage);
    await screen.findByText("Claude 2");
    expect(createCacheGroup()).not.toBeNull();
  });

  it("keeps the pair rule for input/output while cache prices stay independent", async () => {
    serve([model(1, { cache_read_price_per_million: "0.3" })]);
    render(ModelPage);
    const modal = await openEditor();
    await fireEvent.input(within(modal).getByLabelText("출력"), { target: { value: "" } });
    await fireEvent.click(within(modal).getByText("저장"));

    expect(toastError).toHaveBeenCalledWith(PAIR_RULE_MESSAGE);
    expect(patch).not.toHaveBeenCalled();
  });

  it("blocks saving an invalid cache price in the editor and clears stale errors on reopen", async () => {
    serve([model(1)]);
    render(ModelPage);
    let modal = await openEditor();
    await fireEvent.input(within(modal).getByLabelText("캐시 읽기"), { target: { value: "-0.1" } });
    await fireEvent.click(within(modal).getByText("저장"));
    expect(await within(modal).findByText(CACHE_PRICE_ERROR)).toBeTruthy();
    expect(patch).not.toHaveBeenCalled();

    await fireEvent.click(within(modal).getByText("취소"));
    modal = await openEditor();
    expect(within(modal).queryByText(CACHE_PRICE_ERROR)).toBeNull();
    expect((within(modal).getByLabelText("캐시 읽기") as HTMLInputElement).value).toBe("");
  });
});
