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
| Z.AI `zai` | `glm-4.5-flash` | Earlier coding probe passed; live health probe on Oct 15 answered in 12.3 seconds. | Z.AI's exact key/model allowance was not published in the checked docs; use the account console and response headers. Chinese-origin GLM retained. |
| Mistral `mistral` | `ministral-3b-2512` | Earlier free-mode coding check passed; live health probe on Oct 15 answered in 0.7 seconds. | Free mode includes monthly API usage; per-model request-per-second and token-per-minute limits are shown in the account's Limits page. They vary by organization/model, so there is no honest universal number to put here. |
| NVIDIA NIM `nvidia` | `nvidia/nemotron-3-super-120b-a12b` in user config | Oct 15: live health answered; isolated `megazword run -e -m nvidia` coding job completed in 42.0 seconds using five requests; independent pytest: 7 passed. Direct DeepSeek V4.1 Flash previously timed out; DeepSeek Coder 6.7B returned 404. | NVIDIA Developer Program hosted API access is free for prototyping, development, and testing. The current published terms exclude serving real end users without NVIDIA AI Enterprise; no numeric hosted RPM quota was published in the checked docs. |
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
| Groq Qwen 3.8 27B (`groq-qwen`) | Short coding request written in Chinese; asked for `is_even`, Chinese explanation/docstring, and meaningful pytest cases. | Completed in 4.4 seconds using three requests; independent pytest: 5 passed. Chinese-language coding is verified for this small task. This does not establish broad Chinese code-review quality. |
| NVIDIA DeepSeek V4.1 Flash | Tiny direct chat request, 40-second request cap. | Timed out; no result. |
| NVIDIA DeepSeek Coder 6.7B Instruct | Tiny direct chat request. | HTTP 404 for the catalog-listed ID. |

These Chinese-origin models remain in the candidate set. Qwen passed one
English coding task and one short Chinese coding task; broader multilingual
review quality still needs more examples before assigning language-critical
work.

Groq currently provides four separately metered, working model identities under
one key. Google provides two working model identities under its Developer API
key; `gemini` remains the separate Gemini CLI identity. OpenRouter provides one
dynamic identity and five fixed tool-capable identities, but all six share the
same account pool. Mega Zword reads provider request-limit headers and switches
at 5% remaining. It persists a low-water mark across runs until the reported
reset, or one hour if the provider omits a reset header. An HTTP 429 also
triggers immediate failover. Groq aliases share a conservative two-second
call-start pace; that does not merge their provider-reported daily per-model
quotas. Usage from other apps becomes visible when the provider returns fresh
headers.

## Shared pools and candidates not yet usable today

| Provider | Available pool / catalog | Current evidence | Plan |
| --- | --- | --- | --- |
| OpenRouter | 15 zero-priced, tool-capable catalog entries | Before the credit purchase, account meter showed 57/50 requests used and 0 remaining. After the user added $10, the account reports $10 credits, $0 usage, and `is_free_tier=false`. Five fixed IDs passed tool calls at $0; the dynamic router also succeeded. Two Gemma models returned 429 and two Inkling models are app-gated. | Use the free router or one of five verified fixed identities. The $10 purchase unlocks the higher free-request ceiling; it does not guarantee upstream capacity on every model. Check the selected model and returned usage cost. |
| Cloudflare Workers AI | 29 catalog text models eligible for free plan | Oct 15 live health check returned the documented daily-allocation 429; provider Retry-After was 442 minutes to 00:00 UTC. No inference ran. This is one account-shared pool for all models. | Free allocation is 10,000 neurons/day, reset at 00:00 UTC. Do not call again until reset and the account plan/free boundary is confirmed; on Workers Paid, overage beyond the free allocation is billable. |
| Gemini API | 46 `generateContent` catalog IDs | Two Flash-Lite models answered. A preview timed out; three older IDs returned 404 despite catalog metadata. | Keep the two proven models; treat timeout and 404 as unresolved model/API compatibility, not quota exhaustion. |
| NVIDIA NIM | 81 model IDs in account catalog | The configured Nemotron 3 Super endpoint passed both health and isolated coding-plus-tests. | Additional IDs remain untested. The hosted Developer Program terms limit this to development/testing, not user-facing production; do not count catalog presence as a working route. |
| Mistral | 45 model IDs listed | Ministral 3B has passed a coding run and a current health check. | Exact free allowance and per-model limits are account-specific and shown in the Mistral Limits page. |
| Z.AI | 11 model IDs | GLM-4.5-Flash health/coding evidence remains positive; health check repeated Oct 15. | Exact account quota still needs the Z.AI console; retain the one verified identity and avoid catalog-wide probes. |
| Tencent TokenHub | `deepseek-v4-pro` via International Singapore OpenAI-compatible API | Authenticated catalog lists the exact model ID. Two minimal inference probes (direct and selected by Mega Zword's changed default) returned HTTP 402 / business code `401006`. Live Activation page shows this model's 1,000,000-token grant **Claimed**, **100% remaining**, and pay-as-you-go **Not Enabled**, while its default service is **Stopped**. This matches the same mismatch seen for Hy3 despite the model ID and grant being present. The DeepSeek response had no request ID; the earlier Hy3 request ID was `203230e4-3f2f-4d51-a11a-32bd1668a71c`. | Keep as explicit-only until inference succeeds. Do not enable pay-as-you-go. Exact ID and free grant are verified; Tencent's stopped default service/account state is the blocker and needs support investigation. |
| Alibaba Cloud Model Studio | Qwen/Qwen-Coder and other compatible models | New-user free quota is typically 1,000,000 combined input/output tokens per eligible model for 90 days; eligible region and exact model quota vary. OpenAI-compatible Chat Completions supports tool calls. No account/key or live Mega Zword probe yet. | Viable second candidate. Use the general-purpose API key, enable **Free Quota Only** for each model before testing, and verify its remaining quota/expiry in the console. Some verified accounts otherwise continue into billable pay-as-you-go after quota exhaustion. |
| Cerebras | Multiple open models, including Qwen | Current official offer is a one-time $5 promotional credit after adding a valid payment method; it expires in 30 days. It does not auto-enroll or charge, and calls pause when used/expired unless credits are purchased. | Not an ongoing free tier. A trial could be considered separately; current code keeps it out of automatic free routing. |
| SambaNova Cloud | DeepSeek, Llama, Gemma, GPT-OSS, MiniMax | Current Free plan page says add a payment method and purchase credits before first requests; API is pay-as-you-go. | Not currently a no-cost API option; do not add to free failover. |
| Hugging Face Inference Providers | 200+ routed models | Current official billing docs list no included credits for Free accounts; users must purchase credits or upgrade. Older references to $0.10 monthly free credits are stale. | Not a free API source under the current plan. |

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
   persist low-water status and switch at 5% remaining and on 429. Keep reset
   and backoff evidence per identity, not per unrelated provider.
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
[Cloudflare Workers AI limits and errors](https://developers.cloudflare.com/workers-ai/platform/errors/),
[Mistral usage and limits](https://docs.mistral.ai/admin/billing-usage/usage-limits),
[Mistral rate-limit headers](https://docs.mistral.ai/resources/known-limitations),
[OpenRouter free-model limits](https://openrouter.ai/blog/tutorials/how-to-get-the-lowest-cost-llm-inference-on-openrouter/),
[NVIDIA NIM access](https://docs.api.nvidia.com/nim/docs/product).

New-provider research (2026-10-15): [Tencent TokenHub free experience package](https://cloud.tencent.com/document/product/1823/130053), [Tencent TokenHub API quick start](https://cloud.tencent.com/document/product/1823/130058), [Tencent TokenHub Online Inference status and billing modes](https://intl.cloud.tencent.com/ind/document/product/1300/78946), [Tencent TokenHub activation management](https://cloud.tencent.com/document/product/1823/137795), [Tencent TokenHub function-calling guide](https://cloud.tencent.com/document/product/1823/132248), [Alibaba Model Studio free quota and Free Quota Only](https://help.aliyun.com/en/model-studio/new-free-quota), [Alibaba Qwen-Coder capabilities and tool calls](https://help.aliyun.com/en/model-studio/qwen-coder), [Cerebras pricing](https://www.cerebras.ai/pricing), [SambaNova plans](https://cloud.sambanova.ai/plans), and [Hugging Face Inference Provider pricing](https://huggingface.co/docs/inference-providers/en/pricing).
