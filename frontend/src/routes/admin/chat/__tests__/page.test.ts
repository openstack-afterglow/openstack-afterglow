import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/svelte";
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
    confirmDialog: vi.fn(),
    invalidateChatModels: vi.fn(),
    authScope: { token: "token", projectId: "project", isSystemAdmin: true },
    authListeners: new Set<(value: { token: string; projectId: string; isSystemAdmin: boolean }) => void>(),
    ApiError,
  };
});

vi.mock("$lib/stores/auth", () => ({
  auth: {
    subscribe(run: (value: { token: string; projectId: string; isSystemAdmin: boolean }) => void) {
      mocks.authListeners.add(run);
      run(mocks.authScope);
      return () => mocks.authListeners.delete(run);
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
vi.mock("$lib/stores/chatModels", () => ({
  invalidateChatModels: mocks.invalidateChatModels,
}));
vi.mock("$lib/stores/confirm.svelte", () => ({
  confirmDialog: mocks.confirmDialog,
}));
vi.mock("$lib/stores/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const { get, post, patch, put, deleteRequest, confirmDialog, ApiError } = mocks;
function setAuthScope(token: string, projectId: string) {
  mocks.authScope = { token, projectId, isSystemAdmin: true };
  for (const listener of mocks.authListeners) listener(mocks.authScope);
}

import ModelPage from "../models/+page.svelte";
import ProviderPage from "../+page.svelte";
import ToolPage from "../tools/+page.svelte";

const provider = {
  id: 1,
  name: "OpenAI",
  provider_type: "openai",
  api_base: null,
  has_api_key: true,
  has_billing_admin_key: false,
  billing_capability: "openai_admin_usage" as const,
  models_dev_provider_id: "openai",
  is_active: true,
  margin_multiplier: 1,
};

const billingPeriods = { daily: "1", weekly: "2", monthly: "3", total: "4" };
function billingSnapshot(
  providerId: number,
  providerName: string,
  providerType: string,
  overrides: Record<string, unknown> = {},
) {
  return {
    provider_id: providerId,
    provider_name: providerName,
    provider_type: providerType,
    capability: null,
    status: "unsupported",
    reason: "billing_endpoint_unsupported",
    fetched_at: "2026-09-13T00:00:00Z",
    billing_url: null,
    usage_url: null,
    has_billing_admin_key: false,
    local_usage: {
      currency: "USD",
      requests: billingPeriods,
      tokens: { daily: "100", weekly: "200", monthly: "300", total: "400" },
      raw_cost: { daily: "0.5", weekly: "1.5", monthly: "2.5", total: "9.5" },
    },
    provider_usage: null,
    is_available: null,
    is_free_tier: null,
    limit: null,
    remaining: null,
    usage_total: null,
    usage_daily: null,
    usage_weekly: null,
    usage_monthly: null,
    balances: [],
    ...overrides,
  };
}
const chatgptProvider = {
  ...provider,
  id: 7,
  name: "shared-chatgpt",
  provider_type: "chatgpt",
  auth_mode: "chatgpt_device" as const,
  has_api_key: false,
  has_credentials: false,
  auth_status: "disconnected" as const,
  auth_expires_at: null,
};

const claudeSubscriptionProvider = {
  ...provider,
  id: 8,
  name: "shared-claude",
  provider_type: "anthropic",
  auth_mode: "anthropic_subscription" as const,
  has_api_key: false,
  has_credentials: false,
  auth_status: "disconnected" as const,
  auth_expires_at: null,
};
const models = [
  {
    id: 10,
    provider_id: 1,
    model_name: "openai/gpt-test",
    api_model_name: "openai/gpt-test",
    api_provider: "openai",
    display_name: "Test",
    is_active: true,
    input_price_per_million: "2",
    output_price_per_million: "8",
    effective_input_price_per_million: "2",
    effective_output_price_per_million: "8",
    effective_price_source: "models.dev",
    models_dev_model_id: "openai/gpt-test",
    price_source: "models.dev",
  },
  {
    id: 11,
    provider_id: 1,
    model_name: "openai/manual",
    api_model_name: "openai/manual",
    api_provider: "openai",
    display_name: "Manual",
    is_active: true,
    input_price_per_million: "3",
    output_price_per_million: "9",
    models_dev_model_id: null,
    price_source: "manual",
    effective_input_price_per_million: "3",
    effective_output_price_per_million: "9",
    effective_price_source: "manual",
  },
  {
    id: 12,
    provider_id: 1,
    model_name: "perplexity/perplexity/sonar",
    api_model_name: "perplexity/sonar",
    api_provider: "perplexity",
    display_name: null,
    is_active: true,
    input_price_per_million: null,
    output_price_per_million: null,
    effective_input_price_per_million: "5.000000",
    effective_output_price_per_million: "22.500000",
    effective_price_source: "litellm",
    models_dev_model_id: null,
    price_source: null,
  },
];

function queueInitialLoads() {
  get.mockImplementation((path: string) => {
    if (path === "/api/v1/chat/admin/providers")
      return Promise.resolve(provider ? [provider] : []);
    if (path === "/api/v1/chat/admin/models") return Promise.resolve(models);
    if (path === "/api/v1/chat/admin/models/title")
      return Promise.resolve({ model_id: null });
    return Promise.resolve([]);
  });
}
function discoveryResponse(providerId: number, candidates: { id: string; display_name?: string | null; purpose?: "chat" | "non_chat" | "unknown"; input_token_limit?: number | null; output_token_limit?: number | null }[], overrides: Record<string, unknown> = {}) {
  return {
    provider_id: providerId,
    fetched_at: "2026-09-23T10:00:00Z",
    live_status: "success",
    complete: true,
    error: null,
    source: "api",
    models: candidates.map((candidate) => candidate.id),
    candidates,
    ...overrides,
  };
}

describe("admin chat model pricing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.authListeners.clear();
    mocks.authScope = { token: "token", projectId: "project", isSystemAdmin: true };
    queueInitialLoads();
  });

  it("renders price values and their source", async () => {
    render(ModelPage);
    await screen.findByText("models.dev");
    expect(screen.getByText("수동")).toBeTruthy();
    expect(screen.getByText(/입력 2 · 출력 8 USD/)).toBeTruthy();
    expect(screen.getByText(/입력 5 · 출력 22\.5 USD/)).toBeTruthy();
  });

  it("shows canonical API metadata separately from the internal routing ID", async () => {
    const testModels = [
      ...models,
      {
        id: 13,
        provider_id: 1,
        model_name: "perplexity/perplexity/deepseek-v4-flash-0731",
        api_model_name: "perplexity/deepseek-v4-flash-0731",
        api_provider: "perplexity",
        display_name: null,
        is_active: true,
        capabilities: { web_search: true },
        input_price_per_million: null,
        output_price_per_million: null,
        effective_input_price_per_million: null,
        effective_output_price_per_million: null,
        effective_price_source: "unpriced" as const,
        models_dev_model_id: null,
        price_source: null,
      },
    ];
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve(provider ? [provider] : []);
      if (path === "/api/v1/chat/admin/models")
        return Promise.resolve(testModels);
      if (path === "/api/v1/chat/admin/models/title")
        return Promise.resolve({ model_id: null });
      return Promise.resolve([]);
    });
    render(ModelPage);
    expect(await screen.findByText("sonar")).toBeTruthy();
    expect(
      screen.getByText("perplexity/sonar", { selector: "code" }),
    ).toBeTruthy();
    expect(screen.getByText("deepseek-v4-flash-0731")).toBeTruthy();
    expect(screen.getByText("Search")).toBeTruthy();
    expect(
      screen.getByText("perplexity/perplexity/deepseek-v4-flash-0731"),
    ).toBeTruthy();
  });

  it("offers Perplexity Agent, Router, and Sonar transports with exact URL guidance", async () => {
    render(ProviderPage);
    const option = await screen.findByRole("option", {
      name: "Perplexity (Agent API · Router · Sonar)",
    });
    await fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "perplexity" },
    });

    expect(option).toBeTruthy();
    expect(
      await screen.findByText(/https:\/\/api\.perplexity\.ai\/v1/),
    ).toBeTruthy();
    expect(
      screen.getByText(/https:\/\/api\.perplexity\.ai\/router/),
    ).toBeTruthy();
  });

  it("loads one bulk snapshot and renders local usage, live balances, and official payment links", async () => {
    const providers = [
      { ...provider, id: 2, name: "OpenRouter", provider_type: "openrouter" },
      { ...provider, id: 3, name: "DeepSeek", provider_type: "deepseek" },
      { ...provider, id: 4, name: "OpenAI" },
    ];
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve(providers);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path === "/api/v1/chat/admin/providers/billing") {
        return Promise.resolve([
          billingSnapshot(2, "OpenRouter", "openrouter", {
            capability: "openrouter_key",
            status: "available",
            reason: null,
            billing_url: "https://openrouter.ai/settings/credits",
            usage_url: "https://openrouter.ai/activity",
            is_free_tier: false,
            limit: "100",
            remaining: "75",
            usage_total: "25",
            usage_daily: "1",
            usage_weekly: "5",
            usage_monthly: "20",
          }),
          billingSnapshot(3, "DeepSeek", "deepseek", {
            capability: "deepseek_balance",
            status: "available",
            reason: null,
            billing_url: "https://platform.deepseek.com/top_up",
            is_available: true,
            balances: [
              {
                currency: "USD",
                total: "48.5",
                purchased: "40",
                granted: "8.5",
              },
            ],
          }),
          billingSnapshot(4, "OpenAI", "openai", {
            billing_url:
              "https://platform.openai.com/settings/organization/billing/overview",
            usage_url: "https://platform.openai.com/usage",
            local_usage: {
              currency: "USD",
              requests: { ...billingPeriods, monthly: "12" },
              tokens: {
                daily: "100",
                weekly: "200",
                monthly: "12345",
                total: "20000",
              },
              raw_cost: {
                daily: "0.5",
                weekly: "1.5",
                monthly: "7.5",
                total: "19.5",
              },
            },
          }),
        ]);
      }
      return Promise.resolve([]);
    });

    render(ProviderPage);

    expect(await screen.findByText("API 키 남은 한도")).toBeTruthy();
    expect(screen.getByText("API 키 한도 연동")).toBeTruthy();
    expect(screen.getByText("계정 잔액 연동")).toBeTruthy();
    expect(screen.getByText("$75")).toBeTruthy();
    expect(screen.getByText(/계정 전체 선불 잔액이 아닙니다/)).toBeTruthy();
    expect(screen.getByText("현재 계정 잔액")).toBeTruthy();
    expect(screen.getByText("48.5 USD")).toBeTruthy();
    expect(screen.getByText("구매 충전액")).toBeTruthy();
    expect(screen.getByText("40 USD")).toBeTruthy();
    expect(screen.getByText("지급 크레딧")).toBeTruthy();
    expect(screen.getByText("8.5 USD")).toBeTruthy();
    const openAiRow = document.querySelector(
      '[data-provider-id="4"]',
    ) as HTMLElement;
    expect(within(openAiRow).getByText("$7.5")).toBeTruthy();
    expect(within(openAiRow).getByText("12회")).toBeTruthy();
    expect(within(openAiRow).getByText("12,345")).toBeTruthy();
    expect(within(openAiRow).getByText("공식 API 조회 미지원")).toBeTruthy();
    expect(
      within(openAiRow).getByText(
        /현재 선불 잔액과 충전액은 결제 콘솔에서 확인/,
      ),
    ).toBeTruthy();
    const paymentLink = within(openAiRow).getByRole("link", {
      name: "크레딧 충전·결제 ↗",
    });
    expect(paymentLink.getAttribute("href")).toContain(
      "platform.openai.com/settings/organization/billing",
    );
    expect(paymentLink.getAttribute("target")).toBe("_blank");
    expect(paymentLink.getAttribute("rel")).toContain("noreferrer");
    expect(get).toHaveBeenCalledWith(
      "/api/v1/chat/admin/providers/billing",
      "token",
      "project",
    );
    expect(
      get.mock.calls.filter(
        ([path]) => path === "/api/v1/chat/admin/providers/billing",
      ),
    ).toHaveLength(1);
    expect(
      get.mock.calls.some(([path]) =>
        /providers\/\d+\/billing/.test(String(path)),
      ),
    ).toBe(false);
  });

  it("isolates MCP, skills, and custom HTTP tools on the tool settings route", async () => {
    render(ToolPage);
    expect(await screen.findByText("원격 MCP 서버")).toBeTruthy();
    expect(screen.getByText("커스텀 HTTP 툴")).toBeTruthy();
    expect(screen.getByText("스킬")).toBeTruthy();
    expect(screen.queryByText("LLM 프로바이더")).toBeNull();
  });

  it("saves a complete manual price pair with PATCH", async () => {
    render(ModelPage);
    await screen.findAllByText("가격 수정");
    await fireEvent.click(screen.getAllByText("가격 수정")[0]);
    const modal = screen.getByText("모델 가격 수정").parentElement!;
    const inputs = within(modal).getAllByPlaceholderText(/USD \/ 1M tokens/);
    await fireEvent.input(inputs[0], { target: { value: "3" } });
    await fireEvent.input(inputs[1], { target: { value: "9" } });
    await fireEvent.click(screen.getByText("저장"));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        "/api/v1/chat/admin/models/10",
        {
          input_price_per_million: "3",
          output_price_per_million: "9",
          // The editor sends only changed keys; untouched cache prices stay absent.
        },
        "token",
        "project",
      ),
    );
  });

  it("preselects an exact catalog match but preserves manual prices", async () => {
    get.mockImplementation((path: string) => {
      if (
        path.startsWith(
          "/api/v1/chat/admin/models/pricing/models-dev/providers?",
        )
      )
        return Promise.resolve({
          providers: [{ id: "openai", name: "OpenAI", model_count: 2 }],
        });
      if (path.includes("/pricing/models-dev/providers/openai"))
        return Promise.resolve({
          models: [
            {
              id: "openai/gpt-test",
              name: "GPT Test",
              input_price_per_million: "2",
              output_price_per_million: "8",
              price_available: true,
              unsupported_price_fields: ["cost.tiers"],
            },
            {
              id: "openai/manual",
              name: "Manual",
              input_price_per_million: "2",
              output_price_per_million: "8",
              price_available: true,
              unsupported_price_fields: [],
            },
          ],
        });
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve(models);
      if (path === "/api/v1/chat/admin/models/title")
        return Promise.resolve({ model_id: null });
      return Promise.resolve([]);
    });
    render(ModelPage);
    await screen.findAllByText("models.dev 가격");
    await fireEvent.click(screen.getAllByText("models.dev 가격")[0]);
    await screen.findByText("models.dev 추천 가격");
    await screen.findByText(/수동 가격 보존/);
    const checkboxes = screen.getAllByRole("checkbox");
    expect((checkboxes.at(-3) as HTMLInputElement | undefined)?.checked).toBe(
      true,
    );
    expect((checkboxes.at(-2) as HTMLInputElement | undefined)?.disabled).toBe(
      true,
    );
    expect(
      screen.getByText(
        /tier\/cache\/reasoning\/audio 단가는 적용하지 않습니다/,
      ),
    ).toBeTruthy();
  });

  it("searches only the registered catalog candidates", async () => {
    get.mockImplementation((path: string) => {
      if (
        path.startsWith(
          "/api/v1/chat/admin/models/pricing/models-dev/providers?",
        )
      ) {
        return Promise.resolve({
          preferred_provider_ids: ["openai"],
          providers: [
            { id: "openai", name: "OpenAI", model_count: 2 },
            { id: "anthropic", name: "Anthropic", model_count: 15 },
          ],
        });
      }
      if (path.includes("/pricing/models-dev/providers/openai"))
        return Promise.resolve({ models: [] });
      if (path.includes("/pricing/models-dev/providers/anthropic"))
        return Promise.resolve({ models: [] });
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve(models);
      if (path === "/api/v1/chat/admin/models/title")
        return Promise.resolve({ model_id: null });
      return Promise.resolve([]);
    });
    render(ModelPage);
    await screen.findAllByText("models.dev 가격");
    await fireEvent.click(screen.getAllByText("models.dev 가격")[0]);
    const search = await screen.findByRole("searchbox", {
      name: "가격표 프로바이더 검색",
    });
    await fireEvent.input(search, { target: { value: "anth" } });
    const providerSelect = screen.getByLabelText("가격표 프로바이더");
    await waitFor(() =>
      expect(
        within(providerSelect).getByRole("option", { name: "Anthropic (15)" }),
      ).toBeTruthy(),
    );
    expect(
      within(providerSelect).queryByRole("option", { name: "OpenAI (2)" }),
    ).toBeNull();
    await fireEvent.input(search, { target: { value: "missing" } });
    await screen.findByText("검색 조건에 맞는 가격표 프로바이더가 없습니다.");
    expect(
      (
        screen.getByRole("button", {
          name: "선택 가격 적용",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(screen.queryByText("가격표를 불러오는 중…")).toBeNull();
  });

  it("requires an explicit catalog choice when the current provider has no match", async () => {
    get.mockImplementation((path: string) => {
      if (
        path.startsWith(
          "/api/v1/chat/admin/models/pricing/models-dev/providers?",
        )
      ) {
        return Promise.resolve({
          preferred_provider_ids: [],
          providers: [{ id: "anthropic", name: "Anthropic", model_count: 15 }],
        });
      }
      if (path === "/api/v1/chat/admin/providers") {
        return Promise.resolve([
          {
            ...provider,
            name: "Custom gateway",
            provider_type: "custom",
            models_dev_provider_id: null,
          },
        ]);
      }
      if (path === "/api/v1/chat/admin/models") return Promise.resolve(models);
      if (path === "/api/v1/chat/admin/models/title")
        return Promise.resolve({ model_id: null });
      return Promise.resolve([]);
    });
    render(ModelPage);
    await screen.findAllByText("models.dev 가격");
    await fireEvent.click(screen.getAllByText("models.dev 가격")[0]);
    const providerSelect = (await screen.findByLabelText(
      "가격표 프로바이더",
    )) as HTMLSelectElement;
    expect(providerSelect.value).toBe("");
    expect(
      (
        screen.getByRole("button", {
          name: "선택 가격 적용",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  it("keeps the modal open and shows a concrete error when import fails", async () => {
    post.mockRejectedValueOnce(new Error("catalog unavailable"));
    get.mockImplementation((path: string) => {
      if (
        path.startsWith(
          "/api/v1/chat/admin/models/pricing/models-dev/providers?",
        )
      )
        return Promise.resolve({
          providers: [{ id: "openai", name: "OpenAI", model_count: 1 }],
        });
      if (path.includes("/pricing/models-dev/providers/openai"))
        return Promise.resolve({
          models: [
            {
              id: "openai/gpt-test",
              name: "GPT Test",
              input_price_per_million: "2",
              output_price_per_million: "8",
              price_available: true,
              unsupported_price_fields: [],
            },
          ],
        });
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve(models);
      if (path === "/api/v1/chat/admin/models/title")
        return Promise.resolve({ model_id: null });
      return Promise.resolve([]);
    });
    render(ModelPage);
    await screen.findByText("Test");
    await fireEvent.click(screen.getByText("models.dev 가격"));
    await screen.findByText("선택 가격 적용");
    await fireEvent.click(screen.getByText("선택 가격 적용"));
    await screen.findByText("가격 import 실패");
    expect(screen.getByText("models.dev 추천 가격")).toBeTruthy();
  });

  it("clears hidden API credentials and creates a ChatGPT subscription with an explicit auth mode", async () => {
    post.mockResolvedValueOnce(chatgptProvider);
    render(ProviderPage);
    await screen.findByRole("option", { name: "ChatGPT 구독 (실험)" });

    await fireEvent.input(screen.getByLabelText("API Base"), {
      target: { value: "https://private.example/v1" },
    });
    await fireEvent.input(screen.getByLabelText("API 키"), {
      target: { value: "must-be-cleared" },
    });
    const connection = screen.getByRole("combobox");
    await fireEvent.change(connection, {
      target: { value: "chatgpt-subscription" },
    });
    expect(screen.queryByLabelText("API 키")).toBeNull();

    await fireEvent.change(connection, { target: { value: "openai" } });
    expect((screen.getByLabelText("API Base") as HTMLInputElement).value).toBe(
      "",
    );
    expect((screen.getByLabelText("API 키") as HTMLInputElement).value).toBe(
      "",
    );
    await fireEvent.change(connection, {
      target: { value: "chatgpt-subscription" },
    });
    await fireEvent.input(screen.getByPlaceholderText("예: openai-prod"), {
      target: { value: "shared-chatgpt" },
    });
    await fireEvent.click(
      screen.getByRole("button", { name: "+ 프로바이더 추가" }),
    );

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        "/api/v1/chat/admin/providers",
        {
          name: "shared-chatgpt",
          provider_type: "chatgpt",
          auth_mode: "chatgpt_device",
        },
        "token",
        "project",
      ),
    );
    expect(await screen.findByText("ChatGPT 구독 연결")).toBeTruthy();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("keeps a created Claude provider available when token registration fails safely", async () => {
    const tokenValue = "sk-ant-oat01-test-fixture-subscription-token";
    post.mockResolvedValueOnce(claudeSubscriptionProvider);
    put.mockRejectedValueOnce(
      new ApiError(
        JSON.stringify({
          code: "subscription_upstream_unavailable",
          message: "구독 인증 공급자에 연결할 수 없습니다",
        }),
        503,
      ),
    );
    render(ProviderPage);
    await screen.findByRole("option", { name: "Claude 구독 (실험)" });

    await fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "claude-subscription" },
    });
    await fireEvent.input(screen.getByPlaceholderText("예: openai-prod"), {
      target: { value: "shared-claude" },
    });
    await fireEvent.click(
      screen.getByRole("button", { name: "+ 프로바이더 추가" }),
    );
    await screen.findByText("Claude 구독 토큰 등록");
    await fireEvent.input(screen.getByPlaceholderText("setup-token"), {
      target: { value: tokenValue },
    });
    await fireEvent.click(
      screen.getByRole("button", { name: "구독 토큰 등록" }),
    );

    expect(await screen.findByText(/연결할 수 없습니다/)).toBeTruthy();
    expect(post).toHaveBeenCalledTimes(1);
    expect(put).toHaveBeenCalledWith(
      "/api/v1/chat/admin/providers/8/auth/token",
      { token: tokenValue, expires_at: null },
      "token",
      "project",
    );
    expect(screen.queryByText(tokenValue)).toBeNull();
  });

  it("starts ChatGPT device auth explicitly and keeps polling single-flight", async () => {
    const { promise: pollResponse, resolve: resolvePoll } =
      Promise.withResolvers<unknown>();
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve([chatgptProvider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      return Promise.resolve([]);
    });
    post.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers/7/auth/device") {
        return Promise.resolve({
          attempt_id: "attempt-opaque",
          status: "pending",
          verification_uri: "https://auth.openai.com/device",
          user_code: "ABCD-EFGH",
          expires_at: new Date(Date.now() + 600_000).toISOString(),
          interval_seconds: 300,
        });
      }
      if (path.endsWith("/poll")) return pollResponse;
      throw new Error(`unexpected POST ${path}`);
    });
    render(ProviderPage);
    await screen.findByText("shared-chatgpt");
    await fireEvent.click(screen.getByRole("button", { name: "연결" }));

    expect(screen.queryByText("ABCD-EFGH")).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "ChatGPT 연결" }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        "/api/v1/chat/admin/providers/7/auth/device",
        {},
        "token",
        "project",
      ),
    );
    expect(await screen.findByText("ABCD-EFGH")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "지금 확인" }));
    await fireEvent.click(screen.getByRole("button", { name: "확인 중…" }));
    expect(
      post.mock.calls.filter(([path]) => String(path).endsWith("/poll")),
    ).toHaveLength(1);

    resolvePoll({
      attempt_id: "attempt-opaque",
      status: "connected",
      expires_at: new Date(Date.now() + 600_000).toISOString(),
      interval_seconds: 300,
    });
    expect(await screen.findByText("연결 완료")).toBeTruthy();
  });

  it("ignores a late device-start response after the modal closes", async () => {
    const { promise: startResponse, resolve: resolveStart } =
      Promise.withResolvers<unknown>();
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve([chatgptProvider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      return Promise.resolve([]);
    });
    post.mockReturnValueOnce(startResponse);
    render(ProviderPage);
    await screen.findByText("shared-chatgpt");
    await fireEvent.click(screen.getByRole("button", { name: "연결" }));
    await fireEvent.click(screen.getByRole("button", { name: "ChatGPT 연결" }));
    await fireEvent.click(screen.getByRole("button", { name: "닫기" }));

    resolveStart({
      attempt_id: "late-attempt",
      status: "pending",
      verification_uri: "https://auth.openai.com/device",
      user_code: "LATE-CODE",
      expires_at: new Date(Date.now() + 600_000).toISOString(),
      interval_seconds: 1,
    });
    await Promise.resolve();
    expect(screen.queryByText("LATE-CODE")).toBeNull();
    expect(screen.queryByText("ChatGPT 구독 연결")).toBeNull();
  });

  it("preserves opaque subscription model identifiers during registration", async () => {
    const opaqueModel = "chatgpt/gpt-5.2-codex";
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve([chatgptProvider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path === "/api/v1/chat/admin/models/title")
        return Promise.resolve({ model_id: null });
      if (path === "/api/v1/chat/admin/providers/7/available-models") {
        return Promise.resolve(discoveryResponse(7, [{ id: opaqueModel, purpose: "unknown" }], { source: "litellm", live_status: "unsupported", complete: false }));
      }
      return Promise.resolve([]);
    });
    post.mockResolvedValue({});
    render(ModelPage);
    await screen.findAllByRole("option", { name: "shared-chatgpt" });
    await fireEvent.click(
      screen.getByRole("button", { name: "모델 불러오기" }),
    );
    expect(await screen.findByText(/구독 카탈로그 후보/)).toBeTruthy();
    await fireEvent.click(screen.getByRole("checkbox", { name: opaqueModel }));
    await fireEvent.click(screen.getByRole("button", { name: "선택 모델 검토" }));
    expect(post).not.toHaveBeenCalled();
    expect(within(screen.getByTestId("model-registration-review")).getByText(/캐시 단가와 기능은 별도 확인/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "가격 확인 후 등록·활성화" }) as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.click(screen.getByRole("button", { name: "비활성으로 저장" }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        "/api/v1/chat/admin/models",
        { provider_id: 7, model_name: opaqueModel, is_active: false },
        "token",
        "project",
      ),
    );
    await waitFor(() => expect(mocks.invalidateChatModels).toHaveBeenCalledTimes(1));
  });
  it("requires a complete explicit price pair to register and activate without inferring capabilities", async () => {
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path.endsWith("/available-models")) return Promise.resolve(discoveryResponse(1, [{ id: "opaque/id-v1", display_name: "Provider Label", purpose: "chat", input_token_limit: 128000, output_token_limit: 8192 }]));
      return Promise.resolve([]);
    });
    post.mockResolvedValue({});
    render(ModelPage);
    await screen.findAllByRole("option", { name: "OpenAI" });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    await screen.findByRole("checkbox", { name: "opaque/id-v1" });
    await fireEvent.click(screen.getByRole("checkbox", { name: "opaque/id-v1" }));
    await fireEvent.click(screen.getByRole("button", { name: "선택 모델 검토" }));
    const review = screen.getByTestId("model-registration-review");
    expect(within(review).getByText(/입력 한도 128000 · 출력 한도 8192/)).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "표시 이름 · opaque/id-v1" }) as HTMLInputElement).value).toBe("Provider Label");
    expect((screen.getByRole("button", { name: "가격 확인 후 등록·활성화" }) as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.input(screen.getByRole("textbox", { name: "입력 단가 · opaque/id-v1" }), { target: { value: "1.25" } });
    expect((screen.getByRole("button", { name: "비활성으로 저장" }) as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.input(screen.getByRole("textbox", { name: "출력 단가 · opaque/id-v1" }), { target: { value: "5" } });
    await fireEvent.input(screen.getByRole("textbox", { name: "표시 이름 · opaque/id-v1" }), { target: { value: "Reviewed Name" } });
    expect((screen.getByRole("button", { name: "가격 확인 후 등록·활성화" }) as HTMLButtonElement).disabled).toBe(false);
    expect(post).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole("button", { name: "가격 확인 후 등록·활성화" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith(
      "/api/v1/chat/admin/models",
      { provider_id: 1, model_name: "opaque/id-v1", display_name: "Reviewed Name", input_price_per_million: "1.25", output_price_per_million: "5", is_active: true },
      "token", "project",
    ));
    expect(post.mock.calls[0][1]).not.toHaveProperty("capabilities");
    await waitFor(() => expect(mocks.invalidateChatModels).toHaveBeenCalledTimes(1));
  });

  it("fences A success after provider B starts, including stale finally", async () => {
    const a = Promise.withResolvers<unknown>();
    const b = Promise.withResolvers<unknown>();
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider, { ...provider, id: 2, name: "Provider B" }]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path.endsWith("/1/available-models")) return a.promise;
      if (path.endsWith("/2/available-models")) return b.promise;
      return Promise.resolve([]);
    });
    render(ModelPage);
    await screen.findAllByRole("option", { name: "Provider B" });
    await fireEvent.change(screen.getByRole("combobox", { name: "조회 프로바이더" }), { target: { value: "1" } });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    await fireEvent.change(screen.getByRole("combobox", { name: "조회 프로바이더" }), { target: { value: "2" } });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    a.resolve(discoveryResponse(1, [{ id: "old-A", purpose: "chat" }]));
    await Promise.resolve();
    expect(screen.queryByText("old-A")).toBeNull();
    expect(screen.getByText("모델 목록을 불러오는 중…")).toBeTruthy();
    b.resolve(discoveryResponse(2, [{ id: "new-B", purpose: "chat" }]));
    expect(await screen.findByText("new-B")).toBeTruthy();
    expect(screen.queryByText("old-A")).toBeNull();
  });

  it("does not let stale A error or finally dismiss B loading", async () => {
    const a = Promise.withResolvers<unknown>();
    const b = Promise.withResolvers<unknown>();
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider, { ...provider, id: 2, name: "Provider B" }]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path.endsWith("/1/available-models")) return a.promise;
      if (path.endsWith("/2/available-models")) return b.promise;
      return Promise.resolve([]);
    });
    render(ModelPage);
    await screen.findAllByRole("option", { name: "Provider B" });
    await fireEvent.change(screen.getByRole("combobox", { name: "조회 프로바이더" }), { target: { value: "1" } });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    await fireEvent.change(screen.getByRole("combobox", { name: "조회 프로바이더" }), { target: { value: "2" } });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    a.reject(new ApiError("secret upstream detail", 503));
    await Promise.resolve();
    expect(screen.getByText("모델 목록을 불러오는 중…")).toBeTruthy();
    expect(screen.queryByText(/secret upstream detail/)).toBeNull();
    b.resolve(discoveryResponse(2, [], { live_status: "empty" }));
    expect(await screen.findByText(/정상적으로 조회했지만 반환된 모델이 없습니다/)).toBeTruthy();
    expect(screen.getByTestId("discovery-provenance").textContent).toContain("정상 빈 결과");
    expect(mocks.invalidateChatModels).not.toHaveBeenCalled();
  });

  it("fences close and reopen while showing unsupported static provenance", async () => {
    const closed = Promise.withResolvers<unknown>();
    const retried = Promise.withResolvers<unknown>();
    let calls = 0;
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path.endsWith("/available-models")) return ++calls === 1 ? closed.promise : retried.promise;
      return Promise.resolve([]);
    });
    render(ModelPage);
    await screen.findAllByRole("option", { name: "OpenAI" });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    await fireEvent.click(screen.getByRole("button", { name: "조회 닫기" }));
    expect(screen.queryByTestId("model-discovery")).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    closed.resolve(discoveryResponse(1, [{ id: "closed-model" }]));
    await Promise.resolve();
    expect(screen.queryByText("closed-model")).toBeNull();
    expect(screen.getByText("모델 목록을 불러오는 중…")).toBeTruthy();
    retried.resolve(discoveryResponse(1, [{ id: "static-model", display_name: "Visible Label", purpose: "unknown" }], {
      source: "litellm", live_status: "unsupported", complete: false,
    }));
    expect(await screen.findByText("static-model")).toBeTruthy();
    expect(screen.getByText("Visible Label")).toBeTruthy();
    expect(screen.getByTestId("discovery-provenance").textContent).toContain("미지원");
    expect(screen.getByTestId("discovery-provenance").textContent).toContain("불완전");
    await fireEvent.input(screen.getByRole("searchbox", { name: "후보 모델 필터" }), { target: { value: "visible label" } });
    expect(screen.getByRole("checkbox", { name: "static-model" })).toBeTruthy();
  });

  it("keeps failed candidates selected and freezes the provider through sequential registration", async () => {
    const first = Promise.withResolvers<unknown>();
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider, { ...provider, id: 2, name: "Provider B" }]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path.endsWith("/1/available-models")) return Promise.resolve(discoveryResponse(1, [
        { id: "chat-A", purpose: "chat" }, { id: "chat-B", purpose: "unknown" }, { id: "embed-C", purpose: "non_chat" },
      ]));
      return Promise.resolve([]);
    });
    post.mockImplementation((_path: string, body: { model_name: string }) => body.model_name === "chat-A" ? first.promise : Promise.reject(new ApiError("already exists", 409)));
    render(ModelPage);
    await screen.findAllByRole("option", { name: "Provider B" });
    await fireEvent.change(screen.getByRole("combobox", { name: "조회 프로바이더" }), { target: { value: "1" } });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    await screen.findByRole("checkbox", { name: "chat-A" });
    expect((screen.getByRole("checkbox", { name: "embed-C" }) as HTMLInputElement).disabled).toBe(true);
    await fireEvent.click(screen.getByRole("button", { name: "전체 선택" }));
    await fireEvent.click(screen.getByRole("button", { name: "선택 모델 검토" }));
    expect(post).not.toHaveBeenCalled();
    expect(within(screen.getByTestId("model-registration-review")).queryByText("embed-C")).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "비활성으로 저장" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    first.resolve({});
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls.map(([, body]) => body)).toEqual([
      { provider_id: 1, model_name: "chat-A", is_active: false },
      { provider_id: 1, model_name: "chat-B", is_active: false },
    ]);
    await waitFor(() => expect(within(screen.getByTestId("model-registration-review")).getByText("등록 실패 · 이 모델만 재시도")).toBeTruthy());
    expect(within(screen.getByTestId("model-registration-review")).getByText("등록됨 · 재요청하지 않음")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "취소" }));
    expect((screen.getByRole("checkbox", { name: "chat-B" }) as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByRole("checkbox", { name: "chat-A" })).toBeNull();
    expect(mocks.invalidateChatModels).toHaveBeenCalledTimes(1);
  });

  it("retries only failed IDs without reposting successful registrations", async () => {
    let secondAttempts = 0;
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path.endsWith("/available-models")) return Promise.resolve(discoveryResponse(1, [{ id: "first", purpose: "chat" }, { id: "second", purpose: "chat" }]));
      return Promise.resolve([]);
    });
    post.mockImplementation((_path: string, body: { model_name: string }) => body.model_name === "first" || ++secondAttempts > 1
      ? Promise.resolve({}) : Promise.reject(new ApiError("duplicate", 409)));
    render(ModelPage);
    await screen.findAllByRole("option", { name: "OpenAI" });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    await screen.findByRole("checkbox", { name: "first" });
    await fireEvent.click(screen.getByRole("button", { name: "전체 선택" }));
    await fireEvent.click(screen.getByRole("button", { name: "선택 모델 검토" }));
    await fireEvent.click(screen.getByRole("button", { name: "비활성으로 저장" }));
    await screen.findByText("등록 실패 · 이 모델만 재시도");
    await fireEvent.click(await screen.findByRole("button", { name: "비활성으로 저장" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
    expect(post.mock.calls.map(([, body]) => body.model_name)).toEqual(["first", "second", "second"]);
    await waitFor(() => expect(screen.queryByTestId("model-registration-review")).toBeNull());
    expect(mocks.invalidateChatModels).toHaveBeenCalledTimes(2);
  });

  it("stops remaining registration requests when provider or scope changes", async () => {
    const pending = Promise.withResolvers<unknown>();
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider, { ...provider, id: 2, name: "Provider B" }]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path.endsWith("/1/available-models")) return Promise.resolve(discoveryResponse(1, [
        { id: "first", purpose: "chat" }, { id: "second", purpose: "chat" },
      ]));
      return Promise.resolve([]);
    });
    post.mockReturnValue(pending.promise);
    render(ModelPage);
    await screen.findAllByRole("option", { name: "Provider B" });
    await fireEvent.change(screen.getByRole("combobox", { name: "조회 프로바이더" }), { target: { value: "1" } });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    await screen.findByRole("checkbox", { name: "first" });
    await fireEvent.click(screen.getByRole("button", { name: "전체 선택" }));
    await fireEvent.click(screen.getByRole("button", { name: "선택 모델 검토" }));
    await fireEvent.click(screen.getByRole("button", { name: "비활성으로 저장" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await fireEvent.change(screen.getByRole("combobox", { name: "조회 프로바이더" }), { target: { value: "2" } });
    setAuthScope("new-token", "new-project");
    pending.resolve({});
    await Promise.resolve();
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith("/api/v1/chat/admin/models", { provider_id: 1, model_name: "first", is_active: false }, "token", "project");
    expect(screen.queryByTestId("model-discovery")).toBeNull();
  });

  it("labels stored inactive, unknown prices and unknown capability independently", async () => {
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([
        { ...models[0], id: 100, model_name: "no-price", display_name: "No price", is_active: false, effective_price_source: "unpriced", effective_input_price_per_million: null, effective_output_price_per_million: null, capabilities: null, effective_capabilities: null },
        { ...models[0], id: 101, model_name: "basic-price", display_name: "Basic price", is_active: true, capabilities: null, effective_capabilities: null },
      ]);
      return Promise.resolve([]);
    });
    render(ModelPage);
    await screen.findByText("No price");
    expect(screen.getByText("비활성 · 저장됨")).toBeTruthy();
    expect(screen.getByText("활성 · 저장됨")).toBeTruthy();
    expect(screen.getByText("가격 미확인", { selector: ".pill" })).toBeTruthy();
    expect(screen.getByText("기본 텍스트 단가 표시됨")).toBeTruthy();
    expect(screen.getAllByText("고급 기능 미확인")).toHaveLength(2);
    await fireEvent.click(screen.getByRole("button", { name: "활성화" }));
    expect(patch).not.toHaveBeenCalled();
  });
  it("requires explicit capability opt-in without copying transport-gated flags or changing prices", async () => {
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([{ ...models[0], capabilities: null, capability_source: null, effective_capability_source: "litellm", effective_capabilities: { vision: false, reasoning: false, tool_call: false, attachment: false, web_search: true, context_limit: null } }]);
      return Promise.resolve([]);
    });
    patch.mockResolvedValue({});
    render(ModelPage);
    await screen.findByText("고급 기능 미확인");
    await fireEvent.click(screen.getByRole("button", { name: "기능 수정" }));
    expect(screen.getByRole("dialog", { name: "모델 기능 수정" })).toBeTruthy();
    await fireEvent.click(screen.getByRole("checkbox", { name: "이미지 입력 (Vision)" }));
    await fireEvent.input(screen.getByRole("textbox", { name: "컨텍스트 한도" }), { target: { value: "16000" } });
    await fireEvent.click(screen.getByRole("button", { name: "기능 설정 저장" }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith("/api/v1/chat/admin/models/10", {
      capabilities: { vision: true, reasoning: false, tool_call: false, attachment: false, modalities: null, reasoning_options: [], context_limit: 16000 },
    }, "token", "project"));
    expect(patch.mock.calls[0][1]).not.toHaveProperty("input_price_per_million");
    expect(JSON.stringify(patch.mock.calls[0][1])).not.toContain("web_search");
    await waitFor(() => expect(mocks.invalidateChatModels).toHaveBeenCalledTimes(1));
  });
  it("shows a discovered input limit as an editable context draft without saving until confirmed", async () => {
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([{ ...models[0], model_name: "opaque/context-id", is_active: false, capabilities: null, effective_capabilities: { vision: false, context_limit: null }, capability_source: null, effective_capability_source: "litellm" }]);
      if (path.endsWith("/available-models")) return Promise.resolve(discoveryResponse(1, [{ id: "opaque/context-id", input_token_limit: 8192, output_token_limit: 2048, purpose: "chat" }]));
      return Promise.resolve([]);
    });
    render(ModelPage);
    await screen.findAllByRole("option", { name: "OpenAI" });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    await screen.findByTestId("discovery-provenance");
    await fireEvent.click(screen.getByRole("button", { name: "기능 수정" }));
    expect(screen.getByText(/입력 한도 8192 tokens를 컨텍스트 한도 초안/)).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "컨텍스트 한도" }) as HTMLInputElement).value).toBe("8192");
    expect(patch).not.toHaveBeenCalled();
  });

  it("retains stored modalities and reasoning options in a capability override PATCH", async () => {
    const modalities = { input: ["text", "image"], output: ["text"] };
    const reasoningOptions = [{ type: "effort", values: ["low", "high"] }];
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([{ ...models[0], capabilities: { vision: true, reasoning: true, tool_call: false, attachment: false, modalities, reasoning_options: reasoningOptions, context_limit: 32000 }, capability_source: "override", effective_capability_source: "override" }]);
      return Promise.resolve([]);
    });
    patch.mockResolvedValue({});
    render(ModelPage);
    await screen.findByText("관리자 기능 설정 · 실행 미검증");
    await fireEvent.click(screen.getByRole("button", { name: "기능 수정" }));
    await fireEvent.click(screen.getByRole("button", { name: "기능 설정 저장" }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith("/api/v1/chat/admin/models/10", {
      capabilities: { vision: true, reasoning: true, tool_call: false, attachment: false, modalities, reasoning_options: reasoningOptions, context_limit: 32000 },
    }, "token", "project"));
  });

  it("isolates discovery across token and project changes", async () => {
    const oldScope = Promise.withResolvers<unknown>();
    const newScope = Promise.withResolvers<unknown>();
    get.mockImplementation((path: string, token: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path.endsWith("/available-models")) return token === "token" ? oldScope.promise : newScope.promise;
      return Promise.resolve([]);
    });
    render(ModelPage);
    await screen.findAllByRole("option", { name: "OpenAI" });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    setAuthScope("next-token", "next-project");
    await waitFor(() => expect(screen.queryByTestId("model-discovery")).toBeNull());
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    oldScope.reject(new ApiError("old credential error", 403));
    await Promise.resolve();
    expect(screen.getByText("모델 목록을 불러오는 중…")).toBeTruthy();
    expect(screen.queryByText(/old credential error/)).toBeNull();
    newScope.resolve(discoveryResponse(1, [{ id: "new-credential-model", purpose: "chat" }]));
    expect(await screen.findByText("new-credential-model")).toBeTruthy();
    expect(get).toHaveBeenCalledWith("/api/v1/chat/admin/providers/1/available-models", "next-token", "next-project");
  });

  it("retries a safe discovery error without treating it as a normal empty response", async () => {
    let attempts = 0;
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path.endsWith("/available-models")) return Promise.resolve(++attempts === 1
        ? discoveryResponse(1, [{ id: "unsafe-error-candidate", purpose: "chat" }], { source: "none", live_status: "error", complete: false, error: { code: "provider_timeout", message: "연결 시간 초과", retryable: true } })
        : discoveryResponse(1, [{ id: "retry-success", purpose: "chat" }]));
      return Promise.resolve([]);
    });
    render(ModelPage);
    await screen.findAllByRole("option", { name: "OpenAI" });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    expect(await screen.findByText(/연결 시간 초과/)).toBeTruthy();
    expect(screen.getByTestId("discovery-provenance").textContent).toContain("실패");
    expect(screen.queryByText(/정상적으로 조회했지만 반환된 모델이 없습니다/)).toBeNull();
    expect(screen.queryByRole("checkbox", { name: "unsafe-error-candidate" })).toBeNull();
    expect(screen.queryByRole("button", { name: "선택 모델 검토" })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "다시 조회" }));
    expect(await screen.findByText("retry-success")).toBeTruthy();
    expect(screen.queryByText(/연결 시간 초과/)).toBeNull();
    expect(mocks.invalidateChatModels).not.toHaveBeenCalled();
  });

  it("does not render a discovery response after the page is destroyed", async () => {
    const pending = Promise.withResolvers<unknown>();
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers") return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path.endsWith("/available-models")) return pending.promise;
      return Promise.resolve([]);
    });
    const view = render(ModelPage);
    await screen.findAllByRole("option", { name: "OpenAI" });
    await fireEvent.click(screen.getByRole("button", { name: "모델 불러오기" }));
    view.unmount();
    pending.resolve(discoveryResponse(1, [{ id: "late-result" }]));
    await Promise.resolve();
    expect(screen.queryByText("late-result")).toBeNull();
    expect(mocks.invalidateChatModels).not.toHaveBeenCalled();
  });

  it("keeps provider controls available when the bulk billing load fails", async () => {
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path === "/api/v1/chat/admin/providers/billing")
        return Promise.reject(new ApiError("down", 503));
      return Promise.resolve([]);
    });

    render(ProviderPage);

    expect(
      await screen.findByText("결제 상태를 불러오지 못했습니다"),
    ).toBeTruthy();
    expect(screen.getByText(/결제 상태 조회 실패 \(503\)/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "키 변경" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "비활성화" })).toBeTruthy();
  });

  it("shows a loading state and resolves it from the bulk response", async () => {
    let resolveBilling!: (value: unknown[]) => void;
    const pending = new Promise<unknown[]>((resolve) => {
      resolveBilling = resolve;
    });
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path === "/api/v1/chat/admin/providers/billing") return pending;
      return Promise.resolve([]);
    });

    render(ProviderPage);

    expect(
      await screen.findByText("사용량과 결제 상태를 조회하는 중…"),
    ).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "조회 중…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    resolveBilling([billingSnapshot(1, "OpenAI", "openai")]);
    expect(await screen.findByText("공식 콘솔 확인")).toBeTruthy();
  });

  it("does not render non-HTTPS billing actions", async () => {
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve([provider]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path === "/api/v1/chat/admin/providers/billing") {
        return Promise.resolve([
          billingSnapshot(1, "OpenAI", "openai", {
            billing_url: "http://unsafe.example/billing",
          }),
        ]);
      }
      return Promise.resolve([]);
    });

    render(ProviderPage);
    expect(await screen.findByText("공식 콘솔 확인")).toBeTruthy();
    expect(
      screen.queryByRole("link", { name: "크레딧 충전·결제 ↗" }),
    ).toBeNull();
  });

  it("does not fabricate account credit when a supported provider lookup fails", async () => {
    const deepSeek = {
      ...provider,
      id: 3,
      name: "DeepSeek",
      provider_type: "deepseek",
    };
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve([deepSeek]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path === "/api/v1/chat/admin/providers/billing") {
        return Promise.resolve([
          billingSnapshot(3, "DeepSeek", "deepseek", {
            capability: "deepseek_balance",
            status: "unavailable",
            reason: "provider_request_failed",
          }),
        ]);
      }
      return Promise.resolve([]);
    });

    render(ProviderPage);

    expect(await screen.findByText("조회 실패")).toBeTruthy();
    expect(
      screen.getByText(/프로바이더 사용량 API 요청이 실패했습니다/),
    ).toBeTruthy();
    expect(
      screen.getByText(/잔액은 사용량에서 추정하지 않습니다/),
    ).toBeTruthy();
    expect(screen.queryByText("현재 계정 잔액")).toBeNull();
  });

  it("stores and removes an admin usage key while fencing a stale pre-mutation response", async () => {
    const { promise: staleBilling, resolve: resolveStaleBilling } =
      Promise.withResolvers<unknown[]>();
    let hasBillingAdminKey = false;
    let billingRefreshes = 0;
    const freshSnapshot = billingSnapshot(1, "OpenAI", "openai", {
      capability: "openai_admin_usage",
      status: "available",
      reason: null,
      has_billing_admin_key: true,
      provider_usage: {
        source: "openai_admin_usage",
        currency: "USD",
        cost: { daily: "1.25", weekly: "5.5", monthly: "17.25", total: null },
        requests: { daily: "12", weekly: "40", monthly: "96", total: null },
        tokens: { daily: "1200", weekly: "4000", monthly: "9600", total: null },
      },
    });
    get.mockImplementation(
      (
        path: string,
        _token?: string,
        _projectId?: string,
        options?: { refresh?: boolean },
      ) => {
        if (path === "/api/v1/chat/admin/providers") {
          return Promise.resolve([
            { ...provider, has_billing_admin_key: hasBillingAdminKey },
          ]);
        }
        if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
        if (path === "/api/v1/chat/admin/providers/billing") {
          if (!options?.refresh) return staleBilling;
          return Promise.resolve(
            billingRefreshes++ === 0
              ? [freshSnapshot]
              : [
                  billingSnapshot(1, "OpenAI", "openai", {
                    capability: "openai_admin_usage",
                  }),
                ],
          );
        }
        return Promise.resolve([]);
      },
    );
    patch.mockImplementation(
      (_path: string, payload: { billing_admin_key: string | null }) => {
        hasBillingAdminKey = Boolean(payload.billing_admin_key);
        return Promise.resolve({});
      },
    );

    render(ProviderPage);
    await screen.findByText("OpenAI");
    await fireEvent.click(
      screen.getByRole("button", { name: "사용량 키 설정" }),
    );
    expect(await screen.findByText("Inference 키와 별도 보관")).toBeTruthy();
    await fireEvent.input(screen.getByLabelText("OpenAI Admin API 키"), {
      target: { value: "sk-admin-fresh" },
    });
    await fireEvent.click(screen.getByRole("button", { name: "키 설정" }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        "/api/v1/chat/admin/providers/1",
        { billing_admin_key: "sk-admin-fresh" },
        "token",
        "project",
      ),
    );
    expect(await screen.findByText("OpenAI 조직 사용량")).toBeTruthy();
    expect(screen.getByText("$17.25")).toBeTruthy();
    expect(get).toHaveBeenCalledWith(
      "/api/v1/chat/admin/providers/billing",
      "token",
      "project",
      { refresh: true },
    );

    resolveStaleBilling([billingSnapshot(1, "OpenAI", "openai")]);
    await Promise.resolve();
    expect(screen.getByText("OpenAI 조직 사용량")).toBeTruthy();
    expect(screen.queryByText("공식 콘솔 확인")).toBeNull();

    await fireEvent.click(
      screen.getByRole("button", { name: "사용량 키 변경" }),
    );
    await fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "키 변경",
      }),
    );
    await waitFor(() =>
      expect(patch).toHaveBeenLastCalledWith(
        "/api/v1/chat/admin/providers/1",
        { billing_admin_key: null },
        "token",
        "project",
      ),
    );
    expect(
      await screen.findByRole("button", { name: "사용량 키 설정" }),
    ).toBeTruthy();
  });

  it("explains Gemini and Perplexity official billing API limits without requesting admin keys", async () => {
    const gemini = {
      ...provider,
      id: 2,
      name: "Gemini",
      provider_type: "gemini",
      billing_capability: null,
    };
    const perplexity = {
      ...provider,
      id: 3,
      name: "Perplexity",
      provider_type: "perplexity",
      billing_capability: null,
    };
    get.mockImplementation((path: string) => {
      if (path === "/api/v1/chat/admin/providers")
        return Promise.resolve([gemini, perplexity]);
      if (path === "/api/v1/chat/admin/models") return Promise.resolve([]);
      if (path === "/api/v1/chat/admin/providers/billing") {
        return Promise.resolve([
          billingSnapshot(2, "Gemini", "gemini", {
            reason: "provider_console_only",
            billing_url: "https://aistudio.google.com/app/billing",
          }),
          billingSnapshot(3, "Perplexity", "perplexity", {
            reason: "provider_analytics_scope_mismatch",
            billing_url: "https://www.perplexity.ai/settings/api",
          }),
        ]);
      }
      return Promise.resolve([]);
    });

    render(ProviderPage);

    expect(
      await screen.findByText(
        /Gemini 선불 잔액과 거래 내역은 공식 Google AI Studio/,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Enterprise Computer Analytics API는 Computer 제품 분석용/,
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /사용량 키/ })).toBeNull();
  });
});
