# Free model roster and quota plan

Checked 2026-10-15. “Catalog” means a provider lists a model; “answered” means
we made one bounded, tiny request and got a response. These are different
claims. Rates change by plan, model and account, so account headers and provider
dashboards take precedence over this snapshot.

## Verified coding-capable API models

| Provider / identity | Model | Result | Quota evidence and handling |
| --- | --- | --- | --- |
| Groq `groq` | `openai/gpt-oss-20b` | Answered; native tool use works | Groq Free: 30 RPM, 1,000 requests/day, 8K TPM, 200K TPD per model; response headers report remaining requests. |
| Groq `groq-120b` | `openai/gpt-oss-120b` | Answered | Same published per-model limits; distinct model pool. |
| Groq `groq-qwen` | `qwen/qwen3.8-27b` | Answered | Same published per-model limits; Chinese-origin Qwen retained. |
| Groq `groq-allam` | `allam-2-7b` | Answered | Probe header showed 7,000 requests/day. |
| Gemini API `gemini-api` | `gemini-3.5-flash-lite` | Answered; 5 output tokens | Free tier; RPM/TPM/RPD are project- and model-specific in AI Studio. This is separate from Gemini CLI. |
| Gemini API `gemini-api-31-lite` | `gemini-3.1-flash-lite` | Answered; 5 output tokens | Independent per-model quota under the same Google AI project key; shared conservative request pace. |
| Z.AI `zai` | `glm-4.5-flash` | Earlier health probe answered | Exact account limits not yet confirmed. Chinese-origin GLM retained. |
| Mistral `mistral` | `ministral-3b-2512` | Earlier free-mode coding check passed | Account free allowance is shared across API/Studio/Vibe; exact current allowance still needs account-page verification. |
| NVIDIA `nvidia` | `nvidia/nemotron-3-super-120b-a12b` in user config | NVIDIA catalog access confirmed; Nemotron 3.5 Lightning separately completed a tool call through OpenRouter at $0. Direct DeepSeek V4.1 Flash timed out; DeepSeek Coder 6.7B returned 404. | NVIDIA Developer Program supports hosted prototyping endpoints; verify the model/account quota and production terms before counting direct capacity. DeepSeek remains included, with the current direct endpoints marked unresolved. |
| OpenRouter `openrouter` | `openrouter/free` dynamically selects a current free endpoint | Tool-call probe succeeded at $0; OpenRouter selected `nvidia/nemotron-3.5-lightning:free` and returned the expected `finish` tool call. Five fixed catalog models also passed the same tool probe. | The funded account reports $10 credits, $0 usage and is no longer on the free tier. OpenRouter documents 1,000 free-model requests/day at $10+ credits and 20 RPM. Failed attempts may still consume daily requests. |

## OpenRouter exact free catalog: bounded tool-call sweep

The live catalog listed 15 zero-priced, tool-parameter-capable entries. We
tested each fixed ID once with one tiny required `finish` tool call (13 tests);
Gemma 4 26B had already been probed once, and `openrouter/free` had its own
successful tool-call test. Calls were paced below 20 RPM.

| Exact ID / identity | Probe result | Roster treatment |
| --- | --- | --- |
| `dots-studio/dots-3-note-preview:free` / `openrouter-dots` | Tool call returned; cost $0 | Added to selectable roster. |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` / `openrouter-nemotron-nano` | Tool call returned; cost $0 | Added to selectable roster. |
| `nvidia/nemotron-3.5-lightning:free` / `openrouter-nemotron-lightning` | Tool call returned; cost $0 | Added to selectable roster; also selected successfully by dynamic router. |
| `poolside/laguna-s-2.1:free` / `openrouter-laguna-s` | Tool call returned; cost $0 | Added to selectable roster. |
| `poolside/laguna-xs-2.1:free` / `openrouter-laguna-xs` | Tool call returned; cost $0 | Added to selectable roster. |
| `cohere/north-mini-code:free` | HTTP 200, but no required tool call | Not counted as coding worker. |
| `google/gemma-4-26b-a4b-it:free` | HTTP 429 | Upstream endpoint currently unavailable. |
| `google/gemma-4-31b-it:free` | HTTP 429 | Upstream endpoint currently unavailable. |
| `liquid/lfm-2.5-2.6b:free` | HTTP 200, but no required tool call | Not counted as coding worker. |
| `nvidia/nemotron-3-super-120b-a12b:free` | HTTP 200, but no required tool call | Not counted as coding worker. |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | HTTP 200 without usable choice/tool data | Not counted as working. |
| `nvidia/nemotron-3.5-super-vl:free` | HTTP 200, but no required tool call | Not counted as coding worker. |
| `thinkingmachines/inkling-small:free` | HTTP 403: only available on agentic harnesses | App-gated for this API client. |
| `thinkingmachines/inkling:free` | HTTP 403: only available on agentic harnesses | App-gated for this API client. |
| `openrouter/free` | Dynamic route returned a `finish` tool call via Nemotron 3.5 Lightning; cost $0 | Kept as first OpenRouter identity. |

The five fixed OpenRouter identities share one API key, daily request pool and
pacing lock. Automatic fallback tries them after independent provider pools so
one shared OpenRouter allowance is not mistaken for six separate quotas.

## Multilingual candidate checks

| Model | Test | Result |
| --- | --- | --- |
| Groq Qwen 3.8 27B (`groq-qwen`) | Mega Zword created a small Python implementation and pytest file from an English coding request; an independent pytest run was executed in the temporary folder. | Passed; 1 test. |
| Groq Qwen 3.8 27B (`groq-qwen`) | Same task phrased in Chinese, with a 100-second whole-run cap. | Timed out before a result. Chinese-language coding quality is not yet verified for this route; this is a latency/quality observation, not proof of quota exhaustion. |
| NVIDIA DeepSeek V4.1 Flash | Tiny direct chat request, 40-second request cap. | Timed out; no result. |
| NVIDIA DeepSeek Coder 6.7B Instruct | Tiny direct chat request. | HTTP 404 for the catalog-listed ID. |

These Chinese-origin models remain in the candidate set. The passing English
Qwen coding run is enough to retain Qwen as a working coding option; the slow
Chinese-language run should be revisited with a shorter task and then measured
for actual Chinese output before assigning multilingual work.

Groq currently provides four separately metered, working model identities under
one key. Google provides two working model identities under its Developer API
key; `gemini` remains the separate Gemini CLI identity. OpenRouter provides one
dynamic identity and five fixed tool-capable identities, but all six share the
same account pool. Mega Zword checks
provider rate-limit response headers and switches to the next free model on a
subsequent call in the same coding run when 5% or fewer requests remain. On
HTTP 429 it immediately fails over. Groq aliases share a conservative
two-second call-start pace; that does not merge their provider-reported daily
per-model quotas. This measured-header guard applies after a response in the
current run; account usage by other apps is only visible once the provider
reports fresh headers.

## Shared pools and candidates not yet usable today

| Provider | Available pool / catalog | Current evidence | Plan |
| --- | --- | --- | --- |
| OpenRouter | 15 zero-priced, tool-capable catalog entries | Before the credit purchase, account meter showed 57/50 requests used and 0 remaining. After the user added $10, the account reports $10 credits, $0 usage, and `is_free_tier=false`. Five fixed IDs passed tool calls at $0; the dynamic router also succeeded. Two Gemma models returned 429 and two Inkling models are app-gated. | Use the free router or one of five verified fixed identities. The $10 purchase unlocks the higher free-request ceiling; it does not guarantee upstream capacity on every model. Check the selected model and returned usage cost. |
| Cloudflare Workers AI | 29 catalog text models eligible for free plan | Daily 10,000-neuron free allocation exhausted; API reports reset at 00:00 UTC. This blocks all models for the account. | Wait for reset, then test one candidate. Do not fan out probes across the shared pool. |
| Gemini API | 46 `generateContent` catalog IDs | Two Flash-Lite models answered. A preview timed out; three older IDs returned 404 despite catalog metadata. | Keep the two proven models; treat timeout and 404 as unresolved model/API compatibility, not quota exhaustion. |
| NVIDIA NIM | 81 model IDs in account catalog | Catalog fetch works. | Test a small, text/chat-capable multilingual set under the existing prototyping account. |
| Mistral | 45 model IDs listed | One small model has passed the prior free-mode coding check. | Verify shared allowance before expanding probes. |
| Z.AI | 11 model IDs | Existing GLM Flash probe passed; coding-depth/quota evidence incomplete. | Keep GLM in the rotation and record its per-request headers/reset. |

Other listed Groq models include Whisper transcription and Orpheus speech
generation. They may be useful for voice features, but are not coding workers;
prompt-guard/safeguard models are classifiers, not general coding agents.

## Origin and evaluation policy

Country of origin is not an exclusion criterion. Qwen (Alibaba), DeepSeek,
Kimi/Moonshot and GLM/Z.AI remain candidates whenever the exact endpoint is
available and its cost, terms, quota, privacy policy, tool support and measured
quality fit the task. Cloudflare and NVIDIA catalogs can also surface these
families. English prompts do not test multilingual ability; add Chinese and
English coding/review examples to the quality evaluation before assigning
language-specific work. A model’s national origin alone does not establish its
privacy or data-handling policy; check the serving provider’s terms.

## Usage plan

1. Keep providers with independent per-model pools in the failover roster
   (currently Groq's four, Google Gemini's two, and five OpenRouter tool-capable
   identities; the OpenRouter identities share one quota).
2. Read provider-supplied remaining/limit headers after each successful call;
   switch at 5% remaining and on 429. Keep 429 reset/backoff evidence per
   identity, not per unrelated provider.
3. Treat account-shared allocations as a single pool. Do not multiply a shared
   allowance by the number of model names or aliases.
4. Before any expanded test, use a one-request prompt and record the model ID,
   result, elapsed time, response quota headers and whether a request was
   rejected before inference. Avoid blind catalog-wide probes.
5. Keep paid fallback off. OpenRouter states that $10 or more in credits raises
   its free-model ceiling to 1,000 requests/day (still 20 RPM); it is a
   one-time credit purchase, not a subscription. Confirm the checkout total
   including the platform purchase fee before deciding whether to fund it.

Provider references: [Groq rate limits](https://console.groq.com/docs/rate-limits),
[Google Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits),
[Google Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing),
[Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/),
[OpenRouter free-model limits](https://openrouter.ai/blog/tutorials/how-to-get-the-lowest-cost-llm-inference-on-openrouter/),
[NVIDIA NIM access](https://docs.api.nvidia.com/nim/docs/product).
