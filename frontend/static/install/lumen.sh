#!/bin/sh
# Public contract: sh -s -- [CODEX_BASE_URL ANTHROPIC_BASE_URL]
# Requires macOS/Linux, Python 3.11+, and a controlling terminal.
# LUMEN_CA_BUNDLE optionally selects an operator-trusted PEM bundle.
# Codex terminal defaults live in $CODEX_HOME/lumen-cli.config.toml, selected by
# --profile lumen-cli. Root desktop defaults stay untouched unless model opt-in
# is requested; both configs share path validation, private backups and updates.
set +x
set +v
exec python3 - "$@" <<'LUMEN_PY'
import copy
import hashlib
import ipaddress
import json
import math
import os
import re
import secrets
import shlex
import signal
import ssl
import stat
import sys
import termios
from pathlib import Path
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

try:
    import tomllib
except ImportError:
    sys.exit('Lumen installer requires Python 3.11 or newer.')


class Rejected(Exception):
    def __init__(self, label='Invalid inputs or unsafe writable paths.'):
        super().__init__(label)


def require(condition, label='Invalid inputs or unsafe writable paths.'):
    if not condition:
        raise Rejected(label)


def interrupted(signum, frame):
    raise Rejected('Installation interrupted.')


for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGTSTP):
    signal.signal(sig, interrupted)


class Terminal:
    def __init__(self):
        self.fd = None
        try:
            self.fd = os.open('/dev/tty', os.O_RDWR | os.O_NOCTTY)
            require(os.isatty(self.fd))
            self.settings = termios.tcgetattr(self.fd)
        except (OSError, termios.error, Rejected):
            if self.fd is not None:
                os.close(self.fd)
            raise Rejected('A controlling terminal is required.') from None

    def prompt(self, label, secret=False):
        complete = False
        try:
            if secret:
                hidden = copy.deepcopy(self.settings)
                hidden[3] &= ~(termios.ECHO | termios.ECHONL)
                termios.tcsetattr(self.fd, termios.TCSANOW, hidden)
            os.write(self.fd, label.encode())
            data = bytearray()
            while True:
                char = os.read(self.fd, 1)
                require(char)
                if char in (b'\n', b'\r'):
                    break
                data.extend(char)
                require(len(data) <= 4096)
            decoded = data.decode('utf-8')
            complete = True
            return decoded
        finally:
            if not complete:
                termios.tcflush(self.fd, termios.TCIFLUSH)
            termios.tcsetattr(self.fd, termios.TCSANOW, self.settings)
            if secret:
                os.write(self.fd, b'\n')

    def close(self):
        try:
            termios.tcsetattr(self.fd, termios.TCSANOW, self.settings)
        finally:
            os.close(self.fd)


def public_url(value):
    try:
        require(isinstance(value, str) and len(value) <= 2048)
        require(re.fullmatch(r'https://[A-Za-z0-9.\[\]:/-]+(?:[A-Za-z0-9._~/-]*)', value))
        require('?' not in value and '#' not in value and '@' not in value)
        parsed = urlsplit(value)
        require(parsed.scheme == 'https' and parsed.hostname and not parsed.username)
        require(parsed.port is None or 1 <= parsed.port <= 65535)
        require(not parsed.netloc.endswith(':'))
        host = parsed.hostname
        try:
            ipaddress.ip_address(host)
        except ValueError:
            labels = host.rstrip('.').split('.')
            require(len(host) <= 253)
            require(all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in labels))
        require(re.fullmatch(r'/[A-Za-z0-9._~/-]*', parsed.path) or not parsed.path)
        return value.rstrip('/')
    except (Rejected, ValueError):
        raise Rejected('Invalid HTTPS endpoint.') from None


def model_id(value):
    require(isinstance(value, str) and re.fullmatch(r'lumen/[1-9][0-9]{0,18}/[1-9][0-9]{0,18}', value),
            'Invalid server model route ID.')
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        fp.close()
        raise Rejected('Model catalog redirects are not allowed.')


def catalog(base, api_key, ca_bundle):
    context = ssl.create_default_context(cafile=str(ca_bundle))
    opener = build_opener(HTTPSHandler(context=context), NoRedirect())
    request = Request(base + '/cli/models', headers={
        'Authorization': 'Bearer ' + api_key, 'Accept': 'application/json',
    })
    try:
        with opener.open(request, timeout=20) as response:
            content = response.read(4 * 1024 * 1024 + 1)
        require(len(content) <= 4 * 1024 * 1024, 'Model catalog is too large.')
        payload = json.loads(content)
    except HTTPError as error:
        status = error.code
        error.close()
        if status in (401, 403):
            raise Rejected('Model catalog access denied. Use a valid key with models:read scope.') from None
        if status == 404:
            raise Rejected('This endpoint has no Lumen CLI model catalog (/cli/models). Check the Codex base URL '
                           'or upgrade Lumen before rerunning setup.') from None
        raise Rejected('Model catalog request failed (HTTP ' + str(status) + ').') from None
    except (URLError, TimeoutError, ssl.SSLError, ValueError):
        raise Rejected('Could not read the server model catalog. Check the endpoint, network and trusted CA.') from None
    require(isinstance(payload, dict) and isinstance(payload.get('models'), list), 'Invalid server model catalog.')
    require(0 < len(payload['models']) <= 10000, 'The server has no available coding models.')
    models = []
    ids = set()
    for row in payload['models']:
        require(isinstance(row, dict), 'Invalid server model catalog.')
        route = model_id(row.get('id'))
        require(route not in ids, 'Duplicate server model route ID.')
        ids.add(route)
        for name in ('api_model_name', 'display_name', 'provider', 'provider_name', 'provider_type'):
            value = row.get(name)
            require(isinstance(value, str) and 0 < len(value) <= 500
                    and not any(ord(char) < 32 or ord(char) == 127 for char in value),
                    'Invalid server model label.')
        protocols = row.get('protocols')
        require(isinstance(protocols, list) and all(item in ('messages', 'responses') for item in protocols),
                'Invalid server model protocol metadata.')
        require(len(set(protocols)) == len(protocols) and type(row.get('usable')) is bool
                and row['usable'] == bool(protocols), 'Invalid server model availability metadata.')
        reason = row.get('disabled_reason')
        require((row['usable'] and reason is None) or
                (not row['usable'] and isinstance(reason, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,99}', reason)),
                'Invalid server model availability reason.')
        for name in ('input_price_per_million', 'output_price_per_million'):
            require(name in row and (row[name] is None or
                    (isinstance(row[name], str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', row[name]))),
                    'Invalid server model price metadata.')
        # Validate every capability the installer reads once, so later readers
        # never substring-match a string or iterate a scalar.
        caps = row.get('capabilities')
        require(isinstance(caps, dict)
                and (caps.get('context_limit') is None or type(caps['context_limit']) is int)
                and all(caps.get(name) is None or (isinstance(caps[name], list)
                        and all(isinstance(item, str) for item in caps[name]))
                        for name in ('input_modalities', 'output_modalities'))
                and (caps.get('reasoning_options') is None or (isinstance(caps['reasoning_options'], list)
                     and all(isinstance(item, dict) for item in caps['reasoning_options']))),
                'Invalid server model capability metadata.')
        models.append(row)
    require(any('responses' in row['protocols'] for row in models)
            and any('messages' in row['protocols'] for row in models),
            'The server needs at least one usable Messages model and one usable Responses model.')
    return models


def show_models(models):
    print('\nServer coding models (roles do not imply a measured model size or quality):')
    previous = None
    for index, row in enumerate(models, 1):
        group = row['id'].split('/')[1]
        if group != previous:
            print('\n' + row['provider_name'] + ' [' + row['provider'] + '; provider ' + group + ']')
            previous = group
        details = []
        limit = row['capabilities'].get('context_limit')
        if type(limit) is int and limit > 0:
            details.append('context ' + format(limit, ','))
        for label, name in (('in', 'input_price_per_million'), ('out', 'output_price_per_million')):
            price = row.get(name)
            if price is not None:
                details.append(label + ' $' + price + '/1M')
        details.append('/'.join(row['protocols']) or 'unavailable: ' + row['disabled_reason'])
        name = row['display_name']
        if name != row['api_model_name']:
            name += ' (' + row['api_model_name'] + ')'
        print('  ' + str(index) + ') ' + name + ' [' + row['id'] + '] — ' + ', '.join(details))


def choose_model(terminal, models, role, protocol):
    while True:
        answer = terminal.prompt(role + ' model number: ').strip()
        if answer.isascii() and answer.isdigit() and len(answer) <= 5:
            index = int(answer) - 1
            if 0 <= index < len(models):
                row = models[index]
                if protocol in row['protocols']:
                    return row
                print('That model does not support ' + protocol + '; choose a compatible row.')
                continue
        print('Choose a number from the server model list.')


def reasoning_levels(row):
    result = []
    options = row['capabilities'].get('reasoning_options')
    if not isinstance(options, list):
        return result
    for option in options:
        if not isinstance(option, dict) or option.get('type') != 'effort':
            continue
        values = option.get('values')
        if not isinstance(values, list):
            continue
        for effort in values:
            if isinstance(effort, str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,30}', effort) and effort not in result:
                result.append(effort)
    return result


# Vendored generic Codex CLI instructions; unchanged text from rust-v0.160.0.
# Source: https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/models-manager/prompt.md
# SHA-256: ac8ae107a0d72fe3476b430afb161ea4e67da2e446d778aefc44828160559807
# SPDX-License-Identifier: Apache-2.0
# Upstream NOTICE:
# OpenAI Codex
# Copyright 2025 OpenAI
# 
# This project includes code derived from [Ratatui](https://github.com/ratatui/ratatui), licensed under the MIT license.
# Copyright (c) 2016-2022 Florian Dehau
# Copyright (c) 2023-2025 The Ratatui Developers
# 
# Upstream LICENSE:
#                                  Apache License
#                            Version 2.0, January 2004
#                         http://www.apache.org/licenses/
# 
# TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION
# 
# 1.  Definitions.
# 
#     "License" shall mean the terms and conditions for use, reproduction,
#     and distribution as defined by Sections 1 through 9 of this document.
# 
#     "Licensor" shall mean the copyright owner or entity authorized by
#     the copyright owner that is granting the License.
# 
#     "Legal Entity" shall mean the union of the acting entity and all
#     other entities that control, are controlled by, or are under common
#     control with that entity. For the purposes of this definition,
#     "control" means (i) the power, direct or indirect, to cause the
#     direction or management of such entity, whether by contract or
#     otherwise, or (ii) ownership of fifty percent (50%) or more of the
#     outstanding shares, or (iii) beneficial ownership of such entity.
# 
#     "You" (or "Your") shall mean an individual or Legal Entity
#     exercising permissions granted by this License.
# 
#     "Source" form shall mean the preferred form for making modifications,
#     including but not limited to software source code, documentation
#     source, and configuration files.
# 
#     "Object" form shall mean any form resulting from mechanical
#     transformation or translation of a Source form, including but
#     not limited to compiled object code, generated documentation,
#     and conversions to other media types.
# 
#     "Work" shall mean the work of authorship, whether in Source or
#     Object form, made available under the License, as indicated by a
#     copyright notice that is included in or attached to the work
#     (an example is provided in the Appendix below).
# 
#     "Derivative Works" shall mean any work, whether in Source or Object
#     form, that is based on (or derived from) the Work and for which the
#     editorial revisions, annotations, elaborations, or other modifications
#     represent, as a whole, an original work of authorship. For the purposes
#     of this License, Derivative Works shall not include works that remain
#     separable from, or merely link (or bind by name) to the interfaces of,
#     the Work and Derivative Works thereof.
# 
#     "Contribution" shall mean any work of authorship, including
#     the original version of the Work and any modifications or additions
#     to that Work or Derivative Works thereof, that is intentionally
#     submitted to Licensor for inclusion in the Work by the copyright owner
#     or by an individual or Legal Entity authorized to submit on behalf of
#     the copyright owner. For the purposes of this definition, "submitted"
#     means any form of electronic, verbal, or written communication sent
#     to the Licensor or its representatives, including but not limited to
#     communication on electronic mailing lists, source code control systems,
#     and issue tracking systems that are managed by, or on behalf of, the
#     Licensor for the purpose of discussing and improving the Work, but
#     excluding communication that is conspicuously marked or otherwise
#     designated in writing by the copyright owner as "Not a Contribution."
# 
#     "Contributor" shall mean Licensor and any individual or Legal Entity
#     on behalf of whom a Contribution has been received by Licensor and
#     subsequently incorporated within the Work.
# 
# 2.  Grant of Copyright License. Subject to the terms and conditions of
#     this License, each Contributor hereby grants to You a perpetual,
#     worldwide, non-exclusive, no-charge, royalty-free, irrevocable
#     copyright license to reproduce, prepare Derivative Works of,
#     publicly display, publicly perform, sublicense, and distribute the
#     Work and such Derivative Works in Source or Object form.
# 
# 3.  Grant of Patent License. Subject to the terms and conditions of
#     this License, each Contributor hereby grants to You a perpetual,
#     worldwide, non-exclusive, no-charge, royalty-free, irrevocable
#     (except as stated in this section) patent license to make, have made,
#     use, offer to sell, sell, import, and otherwise transfer the Work,
#     where such license applies only to those patent claims licensable
#     by such Contributor that are necessarily infringed by their
#     Contribution(s) alone or by combination of their Contribution(s)
#     with the Work to which such Contribution(s) was submitted. If You
#     institute patent litigation against any entity (including a
#     cross-claim or counterclaim in a lawsuit) alleging that the Work
#     or a Contribution incorporated within the Work constitutes direct
#     or contributory patent infringement, then any patent licenses
#     granted to You under this License for that Work shall terminate
#     as of the date such litigation is filed.
# 
# 4.  Redistribution. You may reproduce and distribute copies of the
#     Work or Derivative Works thereof in any medium, with or without
#     modifications, and in Source or Object form, provided that You
#     meet the following conditions:
# 
#     (a) You must give any other recipients of the Work or
#     Derivative Works a copy of this License; and
# 
#     (b) You must cause any modified files to carry prominent notices
#     stating that You changed the files; and
# 
#     (c) You must retain, in the Source form of any Derivative Works
#     that You distribute, all copyright, patent, trademark, and
#     attribution notices from the Source form of the Work,
#     excluding those notices that do not pertain to any part of
#     the Derivative Works; and
# 
#     (d) If the Work includes a "NOTICE" text file as part of its
#     distribution, then any Derivative Works that You distribute must
#     include a readable copy of the attribution notices contained
#     within such NOTICE file, excluding those notices that do not
#     pertain to any part of the Derivative Works, in at least one
#     of the following places: within a NOTICE text file distributed
#     as part of the Derivative Works; within the Source form or
#     documentation, if provided along with the Derivative Works; or,
#     within a display generated by the Derivative Works, if and
#     wherever such third-party notices normally appear. The contents
#     of the NOTICE file are for informational purposes only and
#     do not modify the License. You may add Your own attribution
#     notices within Derivative Works that You distribute, alongside
#     or as an addendum to the NOTICE text from the Work, provided
#     that such additional attribution notices cannot be construed
#     as modifying the License.
# 
#     You may add Your own copyright statement to Your modifications and
#     may provide additional or different license terms and conditions
#     for use, reproduction, or distribution of Your modifications, or
#     for any such Derivative Works as a whole, provided Your use,
#     reproduction, and distribution of the Work otherwise complies with
#     the conditions stated in this License.
# 
# 5.  Submission of Contributions. Unless You explicitly state otherwise,
#     any Contribution intentionally submitted for inclusion in the Work
#     by You to the Licensor shall be under the terms and conditions of
#     this License, without any additional terms or conditions.
#     Notwithstanding the above, nothing herein shall supersede or modify
#     the terms of any separate license agreement you may have executed
#     with Licensor regarding such Contributions.
# 
# 6.  Trademarks. This License does not grant permission to use the trade
#     names, trademarks, service marks, or product names of the Licensor,
#     except as required for reasonable and customary use in describing the
#     origin of the Work and reproducing the content of the NOTICE file.
# 
# 7.  Disclaimer of Warranty. Unless required by applicable law or
#     agreed to in writing, Licensor provides the Work (and each
#     Contributor provides its Contributions) on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
#     implied, including, without limitation, any warranties or conditions
#     of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
#     PARTICULAR PURPOSE. You are solely responsible for determining the
#     appropriateness of using or redistributing the Work and assume any
#     risks associated with Your exercise of permissions under this License.
# 
# 8.  Limitation of Liability. In no event and under no legal theory,
#     whether in tort (including negligence), contract, or otherwise,
#     unless required by applicable law (such as deliberate and grossly
#     negligent acts) or agreed to in writing, shall any Contributor be
#     liable to You for damages, including any direct, indirect, special,
#     incidental, or consequential damages of any character arising as a
#     result of this License or out of the use or inability to use the
#     Work (including but not limited to damages for loss of goodwill,
#     work stoppage, computer failure or malfunction, or any and all
#     other commercial damages or losses), even if such Contributor
#     has been advised of the possibility of such damages.
# 
# 9.  Accepting Warranty or Additional Liability. While redistributing
#     the Work or Derivative Works thereof, You may choose to offer,
#     and charge a fee for, acceptance of support, warranty, indemnity,
#     or other liability obligations and/or rights consistent with this
#     License. However, in accepting such obligations, You may act only
#     on Your own behalf and on Your sole responsibility, not on behalf
#     of any other Contributor, and only if You agree to indemnify,
#     defend, and hold each Contributor harmless for any liability
#     incurred by, or claims asserted against, such Contributor by reason
#     of your accepting any such warranty or additional liability.
# 
# END OF TERMS AND CONDITIONS
# 
# APPENDIX: How to apply the Apache License to your work.
# 
#       To apply the Apache License to your work, attach the following
#       boilerplate notice, with the fields enclosed by brackets "[]"
#       replaced with your own identifying information. (Don't include
#       the brackets!)  The text should be enclosed in the appropriate
#       comment syntax for the file format. We also recommend that a
#       file or class name and description of purpose be included on the
#       same "printed page" as the copyright notice for easier
#       identification within third-party archives.
# 
# Copyright 2025 OpenAI
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#        http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 
CODEX_BASE_INSTRUCTIONS = r'''You are a coding agent running in the Codex CLI, a terminal-based coding assistant. Codex CLI is an open source project led by OpenAI. You are expected to be precise, safe, and helpful.

Your capabilities:

- Receive user prompts and other context provided by the harness, such as files in the workspace.
- Communicate with the user by streaming thinking & responses, and by making & updating plans.
- Emit function calls to run terminal commands and apply patches. Depending on how this specific run is configured, you can request that these function calls be escalated to the user for approval before running. More on this in the "Sandbox and approvals" section.

Within this context, Codex refers to the open-source agentic coding interface (not the old Codex language model built by OpenAI).

# How you work

## Personality

Your default personality and tone is concise, direct, and friendly. You communicate efficiently, always keeping the user clearly informed about ongoing actions without unnecessary detail. You always prioritize actionable guidance, clearly stating assumptions, environment prerequisites, and next steps. Unless explicitly asked, you avoid excessively verbose explanations about your work.

# AGENTS.md spec
- Repos often contain AGENTS.md files. These files can appear anywhere within the repository.
- These files are a way for humans to give you (the agent) instructions or tips for working within the container.
- Some examples might be: coding conventions, info about how code is organized, or instructions for how to run or test code.
- Instructions in AGENTS.md files:
    - The scope of an AGENTS.md file is the entire directory tree rooted at the folder that contains it.
    - For every file you touch in the final patch, you must obey instructions in any AGENTS.md file whose scope includes that file.
    - Instructions about code style, structure, naming, etc. apply only to code within the AGENTS.md file's scope, unless the file states otherwise.
    - More-deeply-nested AGENTS.md files take precedence in the case of conflicting instructions.
    - Direct system/developer/user instructions (as part of a prompt) take precedence over AGENTS.md instructions.
- The contents of the AGENTS.md file at the root of the repo and any directories from the CWD up to the root are included with the developer message and don't need to be re-read. When working in a subdirectory of CWD, or a directory outside the CWD, check for any AGENTS.md files that may be applicable.

## Responsiveness

### Preamble messages

Before making tool calls, send a brief preamble to the user explaining what you’re about to do. When sending preamble messages, follow these principles and examples:

- **Logically group related actions**: if you’re about to run several related commands, describe them together in one preamble rather than sending a separate note for each.
- **Keep it concise**: be no more than 1-2 sentences, focused on immediate, tangible next steps. (8–12 words for quick updates).
- **Build on prior context**: if this is not your first tool call, use the preamble message to connect the dots with what’s been done so far and create a sense of momentum and clarity for the user to understand your next actions.
- **Keep your tone light, friendly and curious**: add small touches of personality in preambles feel collaborative and engaging.
- **Exception**: Avoid adding a preamble for every trivial read (e.g., `cat` a single file) unless it’s part of a larger grouped action.

**Examples:**

- “I’ve explored the repo; now checking the API route definitions.”
- “Next, I’ll patch the config and update the related tests.”
- “I’m about to scaffold the CLI commands and helper functions.”
- “Ok cool, so I’ve wrapped my head around the repo. Now digging into the API routes.”
- “Config’s looking tidy. Next up is patching helpers to keep things in sync.”
- “Finished poking at the DB gateway. I will now chase down error handling.”
- “Alright, build pipeline order is interesting. Checking how it reports failures.”
- “Spotted a clever caching util; now hunting where it gets used.”

## Planning

You have access to an `update_plan` tool which tracks steps and progress and renders them to the user. Using the tool helps demonstrate that you've understood the task and convey how you're approaching it. Plans can help to make complex, ambiguous, or multi-phase work clearer and more collaborative for the user. A good plan should break the task into meaningful, logically ordered steps that are easy to verify as you go.

Note that plans are not for padding out simple work with filler steps or stating the obvious. The content of your plan should not involve doing anything that you aren't capable of doing (i.e. don't try to test things that you can't test). Do not use plans for simple or single-step queries that you can just do or answer immediately.

Do not repeat the full contents of the plan after an `update_plan` call — the harness already displays it. Instead, summarize the change made and highlight any important context or next step.

Before running a command, consider whether or not you have completed the previous step, and make sure to mark it as completed before moving on to the next step. It may be the case that you complete all steps in your plan after a single pass of implementation. If this is the case, you can simply mark all the planned steps as completed. Sometimes, you may need to change plans in the middle of a task: call `update_plan` with the updated plan and make sure to provide an `explanation` of the rationale when doing so.

Use a plan when:

- The task is non-trivial and will require multiple actions over a long time horizon.
- There are logical phases or dependencies where sequencing matters.
- The work has ambiguity that benefits from outlining high-level goals.
- You want intermediate checkpoints for feedback and validation.
- When the user asked you to do more than one thing in a single prompt
- The user has asked you to use the plan tool (aka "TODOs")
- You generate additional steps while working, and plan to do them before yielding to the user

### Examples

**High-quality plans**

Example 1:

1. Add CLI entry with file args
2. Parse Markdown via CommonMark library
3. Apply semantic HTML template
4. Handle code blocks, images, links
5. Add error handling for invalid files

Example 2:

1. Define CSS variables for colors
2. Add toggle with localStorage state
3. Refactor components to use variables
4. Verify all views for readability
5. Add smooth theme-change transition

Example 3:

1. Set up Node.js + WebSocket server
2. Add join/leave broadcast events
3. Implement messaging with timestamps
4. Add usernames + mention highlighting
5. Persist messages in lightweight DB
6. Add typing indicators + unread count

**Low-quality plans**

Example 1:

1. Create CLI tool
2. Add Markdown parser
3. Convert to HTML

Example 2:

1. Add dark mode toggle
2. Save preference
3. Make styles look good

Example 3:

1. Create single-file HTML game
2. Run quick sanity check
3. Summarize usage instructions

If you need to write a plan, only write high quality plans, not low quality ones.

## Task execution

You are a coding agent. Please keep going until the query is completely resolved, before ending your turn and yielding back to the user. Only terminate your turn when you are sure that the problem is solved. Autonomously resolve the query to the best of your ability, using the tools available to you, before coming back to the user. Do NOT guess or make up an answer.

You MUST adhere to the following criteria when solving queries:

- Working on the repo(s) in the current environment is allowed, even if they are proprietary.
- Analyzing code for vulnerabilities is allowed.
- Showing user code and tool call details is allowed.
- Use the `apply_patch` tool to edit files (NEVER try `applypatch` or `apply-patch`, only `apply_patch`): {"command":["apply_patch","*** Begin Patch\\n*** Update File: path/to/file.py\\n@@ def example():\\n- pass\\n+ return 123\\n*** End Patch"]}

If completing the user's task requires writing or modifying files, your code and final answer should follow these coding guidelines, though user instructions (i.e. AGENTS.md) may override these guidelines:

- Fix the problem at the root cause rather than applying surface-level patches, when possible.
- Avoid unneeded complexity in your solution.
- Do not attempt to fix unrelated bugs or broken tests. It is not your responsibility to fix them. (You may mention them to the user in your final message though.)
- Update documentation as necessary.
- Keep changes consistent with the style of the existing codebase. Changes should be minimal and focused on the task.
- Use `git log` and `git blame` to search the history of the codebase if additional context is required.
- NEVER add copyright or license headers unless specifically requested.
- Do not waste tokens by re-reading files after calling `apply_patch` on them. The tool call will fail if it didn't work. The same goes for making folders, deleting folders, etc.
- Do not `git commit` your changes or create new git branches unless explicitly requested.
- Do not add inline comments within code unless explicitly requested.
- Do not use one-letter variable names unless explicitly requested.
- NEVER output inline citations like "【F:README.md†L5-L14】" in your outputs. The CLI is not able to render these so they will just be broken in the UI. Instead, if you output valid filepaths, users will be able to click on them to open the files in their editor.

## Validating your work

If the codebase has tests or the ability to build or run, consider using them to verify that your work is complete. 

When testing, your philosophy should be to start as specific as possible to the code you changed so that you can catch issues efficiently, then make your way to broader tests as you build confidence. If there's no test for the code you changed, and if the adjacent patterns in the codebases show that there's a logical place for you to add a test, you may do so. However, do not add tests to codebases with no tests.

Similarly, once you're confident in correctness, you can suggest or use formatting commands to ensure that your code is well formatted. If there are issues you can iterate up to 3 times to get formatting right, but if you still can't manage it's better to save the user time and present them a correct solution where you call out the formatting in your final message. If the codebase does not have a formatter configured, do not add one.

For all of testing, running, building, and formatting, do not attempt to fix unrelated bugs. It is not your responsibility to fix them. (You may mention them to the user in your final message though.)

Be mindful of whether to run validation commands proactively. In the absence of behavioral guidance:

- When running in the non-interactive approval mode **never**, proactively run tests, lint and do whatever you need to ensure you've completed the task.
- When working in interactive approval modes like **untrusted**, or **on-request**, hold off on running tests or lint commands until the user is ready for you to finalize your output, because these commands take time to run and slow down iteration. Instead suggest what you want to do next, and let the user confirm first.
- When working on test-related tasks, such as adding tests, fixing tests, or reproducing a bug to verify behavior, you may proactively run tests regardless of approval mode. Use your judgement to decide whether this is a test-related task.

## Ambition vs. precision

For tasks that have no prior context (i.e. the user is starting something brand new), you should feel free to be ambitious and demonstrate creativity with your implementation.

If you're operating in an existing codebase, you should make sure you do exactly what the user asks with surgical precision. Treat the surrounding codebase with respect, and don't overstep (i.e. changing filenames or variables unnecessarily). You should balance being sufficiently ambitious and proactive when completing tasks of this nature.

You should use judicious initiative to decide on the right level of detail and complexity to deliver based on the user's needs. This means showing good judgment that you're capable of doing the right extras without gold-plating. This might be demonstrated by high-value, creative touches when scope of the task is vague; while being surgical and targeted when scope is tightly specified.

## Sharing progress updates

For especially longer tasks that you work on (i.e. requiring many tool calls, or a plan with multiple steps), you should provide progress updates back to the user at reasonable intervals. These updates should be structured as a concise sentence or two (no more than 8-10 words long) recapping progress so far in plain language: this update demonstrates your understanding of what needs to be done, progress so far (i.e. files explores, subtasks complete), and where you're going next.

Before doing large chunks of work that may incur latency as experienced by the user (i.e. writing a new file), you should send a concise message to the user with an update indicating what you're about to do to ensure they know what you're spending time on. Don't start editing or writing large files before informing the user what you are doing and why.

The messages you send before tool calls should describe what is immediately about to be done next in very concise language. If there was previous work done, this preamble message should also include a note about the work done so far to bring the user along.

## Presenting your work and final message

Your final message should read naturally, like an update from a concise teammate. For casual conversation, brainstorming tasks, or quick questions from the user, respond in a friendly, conversational tone. You should ask questions, suggest ideas, and adapt to the user’s style. If you've finished a large amount of work, when describing what you've done to the user, you should follow the final answer formatting guidelines to communicate substantive changes. You don't need to add structured formatting for one-word answers, greetings, or purely conversational exchanges.

You can skip heavy formatting for single, simple actions or confirmations. In these cases, respond in plain sentences with any relevant next step or quick option. Reserve multi-section structured responses for results that need grouping or explanation.

The user is working on the same computer as you, and has access to your work. As such there's no need to show the full contents of large files you have already written unless the user explicitly asks for them. Similarly, if you've created or modified files using `apply_patch`, there's no need to tell users to "save the file" or "copy the code into a file"—just reference the file path.

If there's something that you think you could help with as a logical next step, concisely ask the user if they want you to do so. Good examples of this are running tests, committing changes, or building out the next logical component. If there’s something that you couldn't do (even with approval) but that the user might want to do (such as verifying changes by running the app), include those instructions succinctly.

Brevity is very important as a default. You should be very concise (i.e. no more than 10 lines), but can relax this requirement for tasks where additional detail and comprehensiveness is important for the user's understanding.

### Final answer structure and style guidelines

You are producing plain text that will later be styled by the CLI. Follow these rules exactly. Formatting should make results easy to scan, but not feel mechanical. Use judgment to decide how much structure adds value.

**Section Headers**

- Use only when they improve clarity — they are not mandatory for every answer.
- Choose descriptive names that fit the content
- Keep headers short (1–3 words) and in `**Title Case**`. Always start headers with `**` and end with `**`
- Leave no blank line before the first bullet under a header.
- Section headers should only be used where they genuinely improve scanability; avoid fragmenting the answer.

**Bullets**

- Use `-` followed by a space for every bullet.
- Merge related points when possible; avoid a bullet for every trivial detail.
- Keep bullets to one line unless breaking for clarity is unavoidable.
- Group into short lists (4–6 bullets) ordered by importance.
- Use consistent keyword phrasing and formatting across sections.

**Monospace**

- Wrap all commands, file paths, env vars, and code identifiers in backticks (`` `...` ``).
- Apply to inline examples and to bullet keywords if the keyword itself is a literal file/command.
- Never mix monospace and bold markers; choose one based on whether it’s a keyword (`**`) or inline code/path (`` ` ``).

**File References**
When referencing files in your response, make sure to include the relevant start line and always follow the below rules:
  * Use inline code to make file paths clickable.
  * Each reference should have a stand alone path. Even if it's the same file.
  * Accepted: absolute, workspace‑relative, a/ or b/ diff prefixes, or bare filename/suffix.
  * Line/column (1‑based, optional): :line[:column] or #Lline[Ccolumn] (column defaults to 1).
  * Do not use URIs like file://, vscode://, or https://.
  * Do not provide range of lines
  * Examples: src/app.ts, src/app.ts:42, b/server/index.js#L10, C:\repo\project\main.rs:12:5

**Structure**

- Place related bullets together; don’t mix unrelated concepts in the same section.
- Order sections from general → specific → supporting info.
- For subsections (e.g., “Binaries” under “Rust Workspace”), introduce with a bolded keyword bullet, then list items under it.
- Match structure to complexity:
  - Multi-part or detailed results → use clear headers and grouped bullets.
  - Simple results → minimal headers, possibly just a short list or paragraph.

**Tone**

- Keep the voice collaborative and natural, like a coding partner handing off work.
- Be concise and factual — no filler or conversational commentary and avoid unnecessary repetition
- Use present tense and active voice (e.g., “Runs tests” not “This will run tests”).
- Keep descriptions self-contained; don’t refer to “above” or “below”.
- Use parallel structure in lists for consistency.

**Don’t**

- Don’t use literal words “bold” or “monospace” in the content.
- Don’t nest bullets or create deep hierarchies.
- Don’t output ANSI escape codes directly — the CLI renderer applies them.
- Don’t cram unrelated keywords into a single bullet; split for clarity.
- Don’t let keyword lists run long — wrap or reformat for scanability.

Generally, ensure your final answers adapt their shape and depth to the request. For example, answers to code explanations should have a precise, structured explanation with code references that answer the question directly. For tasks with a simple implementation, lead with the outcome and supplement only with what’s needed for clarity. Larger changes can be presented as a logical walkthrough of your approach, grouping related steps, explaining rationale where it adds value, and highlighting next actions to accelerate the user. Your answers should provide the right level of detail while being easily scannable.

For casual greetings, acknowledgements, or other one-off conversational messages that are not delivering substantive information or structured results, respond naturally without section headers or bullet formatting.

# Tool Guidelines

## Shell commands

When using the shell, you must adhere to the following guidelines:

- When searching for text or files, prefer using `rg` or `rg --files` respectively because `rg` is much faster than alternatives like `grep`. (If the `rg` command is not found, then use alternatives.)
- Do not use python scripts to attempt to output larger chunks of a file.

## `update_plan`

A tool named `update_plan` is available to you. You can use it to keep an up‑to‑date, step‑by‑step plan for the task.

To create a new plan, call `update_plan` with a short list of 1‑sentence steps (no more than 5-7 words each) with a `status` for each step (`pending`, `in_progress`, or `completed`).

When steps have been completed, use `update_plan` to mark each finished step as `completed` and the next step you are working on as `in_progress`. There should always be exactly one `in_progress` step until everything is done. You can mark multiple items as complete in a single `update_plan` call.

If all steps are complete, ensure you call `update_plan` to mark all steps as `completed`.
'''



def codex_models(roles):
    require(hashlib.sha256(CODEX_BASE_INSTRUCTIONS.encode()).hexdigest() ==
            "ac8ae107a0d72fe3476b430afb161ea4e67da2e446d778aefc44828160559807",
            'Vendored native Codex instructions integrity check failed.')
    entries = {}
    for role in ('sol', 'luna'):
        row = roles[role]
        if row['id'] in entries:
            entries[row['id']]['display_name'] = 'Sol / Luna — ' + row['provider_name'] + ' / ' + row['display_name']
            continue
        levels = reasoning_levels(row)
        caps = row['capabilities']
        entry = {
            'slug': row['id'],
            'display_name': role.title() + ' — ' + row['provider_name'] + ' / ' + row['display_name'],
            'description': row['provider'] + ' / ' + row['api_model_name'],
            'default_reasoning_level': 'medium' if 'medium' in levels else levels[0] if levels else None,
            'supported_reasoning_levels': [{'effort': effort, 'description': 'Provider-advertised ' + effort} for effort in levels],
            'shell_type': 'unified_exec', 'visibility': 'list', 'supported_in_api': True,
            'priority': len(entries), 'availability_nux': None, 'upgrade': None,
            'support_verbosity': False, 'default_verbosity': None, 'apply_patch_tool_type': None,
            'base_instructions': CODEX_BASE_INSTRUCTIONS,
            'include_apps_usage_instructions': False,
            'supports_reasoning_summary_parameter': False,
            'truncation_policy': {'mode': 'bytes', 'limit': 10000},
            'experimental_supported_tools': [],
            'input_modalities': ['text'] + (['image'] if 'image' in (caps.get('input_modalities') or []) else []),
        }
        limit = caps.get('context_limit')
        if type(limit) is int and limit > 0:
            entry['context_window'] = limit
            entry['max_context_window'] = limit
        entries[row['id']] = entry
    return (json.dumps({'models': list(entries.values())}, ensure_ascii=False, indent=2) + '\n').encode()


def absolute(value):
    require(value and os.path.isabs(value) and '\x00' not in value)
    require(not any(ord(char) < 32 or ord(char) == 127 for char in value))
    require('..' not in Path(value).parts)
    return Path(os.path.normpath(value))


class Files:
    """Anchor operations to no-follow directory descriptors, including ancestors."""
    def __init__(self):
        self.dirs = {Path('/'): os.open('/', os.O_RDONLY | os.O_DIRECTORY)}
        self.snapshots = {}
        self.temps = []

    def directory(self, path, create=False):
        if path in self.dirs:
            return self.dirs[path]
        parent = self.directory(path.parent, create)
        if parent is None:
            return None
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        except FileNotFoundError:
            if not create:
                return None
            os.mkdir(path.name, 0o700, dir_fd=parent)
            fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        info = os.fstat(fd)
        try:
            require(info.st_uid in (0, os.getuid()))
            require(not info.st_mode & 0o022 or (info.st_uid == 0 and info.st_mode & stat.S_ISVTX))
        except BaseException:
            os.close(fd)
            raise
        self.dirs[path] = fd
        return fd

    def read(self, path):
        parent = self.directory(path.parent)
        if parent is None:
            self.snapshots[path] = None
            return None
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            self.snapshots[path] = None
            return None
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid())
            require(not info.st_mode & 0o022 and info.st_size <= 4 * 1024 * 1024)
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                content = stream.read()
            self.snapshots[path] = (info.st_ino, info.st_dev, info.st_mtime_ns, info.st_size, info.st_mode, content)
            return content
        finally:
            os.close(fd)

    def unchanged(self, path):
        previous = self.snapshots[path]
        self.read(path)
        require(self.snapshots[path] == previous)

    def temporary(self, path, content, kind, mode=0o600):
        parent = self.directory(path.parent, True)
        name = '.' + path.name + '.lumen-' + kind + '-' + secrets.token_hex(12)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        self.temps.append((parent, name))
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        return parent, name

    def install(self, changes, private_dirs, key_path, profiles):
        # All content and paths have been validated before the first mutation.
        staged = []
        committed = []
        backups = []
        modes = {path: (stat.S_IMODE(self.snapshots[path][-2])
                        if path in profiles and self.snapshots[path] is not None else 0o600)
                 for path in changes}
        try:
            for path, content in changes.items():
                self.unchanged(path)
                old = self.snapshots[path]
                if old is not None and old[-1] == content:
                    continue
                staged.append((path, self.temporary(path, content, 'pending', modes[path])))
                if old is not None and path != key_path:
                    backups.append(self.temporary(path, old[-1], 'backup'))
            for path in private_dirs:
                fd = self.directory(path, True)
                require(os.fstat(fd).st_uid == os.getuid())
                os.fchmod(fd, 0o700)
            for path, (parent, name) in staged:
                self.unchanged(path)
                os.replace(name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
                committed.append(path)
                os.fsync(parent)
            # Tighten permissions even on an otherwise identical rerun.
            for path in changes:
                parent = self.directory(path.parent)
                fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    os.fchmod(fd, modes[path])
                finally:
                    os.close(fd)
            for backup in backups:
                self.temps.remove(backup)
        except BaseException:
            for path in reversed(committed):
                parent = self.directory(path.parent)
                old = self.snapshots[path]
                if old is None:
                    os.unlink(path.name, dir_fd=parent)
                else:
                    _, name = self.temporary(path, old[-1], 'rollback', stat.S_IMODE(old[-2]))
                    os.replace(name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            raise

    def close(self):
        for parent, name in self.temps:
            try:
                os.unlink(name, dir_fd=parent)
            except FileNotFoundError:
                pass
        for fd in self.dirs.values():
            os.close(fd)


def toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return '[' + ', '.join(toml_value(item) for item in value) + ']'
    if isinstance(value, dict):
        return '{ ' + ', '.join(json.dumps(key) + ' = ' + toml_value(item) for key, item in value.items()) + ' }'
    return value.isoformat()


def key_path(tree):
    path = []
    while isinstance(tree, dict) and len(tree) == 1:
        key, tree = next(iter(tree.items()))
        path.append(key)
    return tuple(path)


def get(tree, path):
    for key in path:
        tree = tree[key]
    return tree


def put(tree, path, value):
    for key in path[:-1]:
        tree = tree.setdefault(key, {})
        require(isinstance(tree, dict))
    tree[path[-1]] = value


def same(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(same(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    if isinstance(left, float) and isinstance(right, float) and math.isnan(left) and math.isnan(right):
        return True
    return left == right


def codex_config(text, base, root_settings, provider='lumen', clear_selector=False):
    if text and not text.endswith('\n'):
        text += '\n'
    original = tomllib.loads(text)
    desired = {('model_providers', provider, key): value for key, value in {
        'name': 'Lumen Responses', 'base_url': base, 'env_key': 'LUMEN_API_KEY',
        'wire_api': 'responses', 'requires_openai_auth': False, 'supports_websockets': False,
    }.items()}
    desired.update({(key,): value for key, value in root_settings.items()})
    expected = copy.deepcopy(original)
    selector = ('model_providers', provider, 'http_headers', 'X-Lumen-Provider')
    if clear_selector:
        headers = expected.get('model_providers', {}).get(provider, {}).get('http_headers', {})
        if isinstance(headers, dict):
            headers.pop(selector[-1], None)
    for path, value in desired.items():
        put(expected, path, value)

    # Parse complete TOML statements rather than matching lines inside strings,
    # arrays, comments, or nested tables. Preserve untouched statements verbatim.
    statements = []
    pending = ''
    for line in text.splitlines(keepends=True):
        pending += line
        try:
            parsed = tomllib.loads(pending)
        except tomllib.TOMLDecodeError:
            continue
        statements.append((pending, parsed))
        pending = ''
    require(not pending)
    remaining = dict(desired)
    context = ()
    output = []
    provider_insert = None
    dotted_insert = None
    first_table = None
    for statement, parsed in statements:
        stripped = statement.lstrip()
        if stripped.startswith('['):
            if first_table is None:
                first_table = len(output)
            # An array-of-tables cannot be the provider being installed.
            context = key_path(parsed)
            if context == ('model_providers', provider) and not stripped.startswith('[['):
                provider_insert = len(output) + 1
            output.append(statement)
            continue
        if not parsed:
            output.append(statement)
            continue
        # Find the assignment's key independently of its possibly inline value.
        # Quoted keys can contain '='; choose the first parseable key prefix.
        assignment = None
        for index, char in enumerate(statement):
            if char != '=':
                continue
            try:
                assignment = key_path(tomllib.loads(statement[:index] + '= 0'))
                lhs = statement[:index].strip()
                break
            except tomllib.TOMLDecodeError:
                pass
        require(assignment is not None)
        path = context + assignment
        if clear_selector and path == selector:
            continue
        clears_selector = clear_selector and selector[:len(path)] == path
        affected = [target for target in desired if target[:len(path)] == path]
        if affected or clears_selector:
            value = copy.deepcopy(get(parsed, assignment))
            for target in affected:
                if target == path:
                    value = desired[target]
                else:
                    require(isinstance(value, dict))
                    put(value, target[len(path):], desired[target])
                remaining.pop(target, None)
            removed = False
            if clears_selector:
                relative = selector[len(path):]
                headers = value
                for key in relative[:-1]:
                    headers = headers.get(key, {}) if isinstance(headers, dict) else {}
                if isinstance(headers, dict) and relative[-1] in headers:
                    headers.pop(relative[-1])
                    removed = True
            if not affected and not removed:
                output.append(statement)
                continue
            output.append(lhs + ' = ' + toml_value(value) + '\n')
            if path[:2] == ('model_providers', provider) and len(context) < 2:
                dotted_insert = (len(output), context)
        else:
            output.append(statement)
    roots = {path: value for path, value in remaining.items() if len(path) == 1}
    if roots:
        position = first_table if first_table is not None else len(output)
        fields = ''.join(path[0] + ' = ' + toml_value(value) + '\n' for path, value in roots.items())
        output.insert(position, fields)
        if dotted_insert is not None and position <= dotted_insert[0]:
            dotted_insert = (dotted_insert[0] + 1, dotted_insert[1])
        if provider_insert is not None and (first_table is None or first_table < provider_insert):
            provider_insert += 1
        for path in roots:
            remaining.pop(path)
    fields = ''.join(path[-1] + ' = ' + toml_value(value) + '\n' for path, value in remaining.items())
    if fields:
        if provider_insert is not None:
            output.insert(provider_insert, fields)
        elif dotted_insert is not None:
            position, prefix = dotted_insert
            fields = ''.join('.'.join(path[len(prefix):]) + ' = ' + toml_value(value) + '\n'
                             for path, value in remaining.items())
            output.insert(position, fields)
        else:
            output.append('\n[model_providers.' + provider + ']\n' + fields)
    result = ''.join(output)
    require(same(tomllib.loads(result), expected))
    return result


START = '# >>> Lumen CLI >>>'
END = '# <<< Lumen CLI <<<'


def profile(text, block):
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.rstrip('\r\n') == START]
    ends = [index for index, line in enumerate(lines) if line.rstrip('\r\n') == END]
    require(len(starts) == len(ends) and len(starts) <= 1)
    if starts:
        require(starts[0] < ends[0])
        return ''.join(lines[:starts[0]]) + block + ''.join(lines[ends[0] + 1:])
    return text + ('' if not text or text.endswith('\n') else '\n') + block


def run():
    require(sys.platform in ('darwin', 'linux'))
    require(len(sys.argv) in (1, 3))
    tty = None
    files = Files()
    try:
        if len(sys.argv) == 3:
            codex, anthropic = map(public_url, sys.argv[1:])
        else:
            tty = Terminal()
            codex = public_url(tty.prompt('Codex HTTPS base URL: '))
            anthropic = public_url(tty.prompt('Anthropic HTTPS base URL: '))
        home = absolute(os.environ.get('HOME', ''))
        codex_home = absolute(os.environ.get('CODEX_HOME', str(home / '.codex')))
        zdotdir = absolute(os.environ.get('ZDOTDIR', str(home)))
        config_home = absolute(os.environ.get('XDG_CONFIG_HOME', str(home / '.config')))
        private = config_home / 'lumen'
        key = private / 'key.sh'
        config = codex_home / 'config.toml'
        cli_config = codex_home / 'lumen-cli.config.toml'
        cli_configs = {'cli': cli_config, 'sol': codex_home / 'lumen-sol.config.toml',
                       'luna': codex_home / 'lumen-luna.config.toml'}
        models_path = codex_home / 'lumen-models.json'
        candidates = [home / name for name in ('.bash_profile', '.bash_login', '.profile')]
        # Inspect every login candidate, including symlinks, before selecting one.
        login_contents = {path: files.read(path) for path in candidates}
        login = next((path for path in candidates if login_contents[path] is not None), home / '.profile')
        profiles = list(dict.fromkeys([home / '.bashrc', login, zdotdir / '.zshrc']))
        old = {path: files.read(path) for path in [key, config, models_path, *cli_configs.values(), *profiles]}
        for directory in (home, codex_home, zdotdir, private):
            fd = files.directory(directory)
            if fd is not None:
                require(os.fstat(fd).st_uid == os.getuid())
        config_text = (old[config] or b'').decode('utf-8')
        tomllib.loads(config_text)
        cli_texts = {path: (old[path] or b'').decode('utf-8') for path in cli_configs.values()}
        for text in cli_texts.values():
            tomllib.loads(text)
        # Check profile markers before asking for a credential.
        for path in profiles:
            profile((old[path] or b'').decode('utf-8'), START + '\n' + END + '\n')
        paths = (['/private/etc/ssl/cert.pem', '/etc/ssl/cert.pem'] if sys.platform == 'darwin' else
                 ['/etc/ssl/certs/ca-certificates.crt', '/etc/pki/tls/certs/ca-bundle.crt', '/etc/ssl/cert.pem'])
        explicit_bundle = os.environ.get('LUMEN_CA_BUNDLE')
        bundle = explicit_bundle or os.environ.get('CODEX_CA_CERTIFICATE')
        if bundle:
            ca = absolute(bundle)
        else:
            ca = next((Path(path) for path in paths if os.path.isfile(path)), None)
            require(ca is not None, 'A trusted CA bundle is required.')
        # CA bundles are read-only inputs, not mutation targets. Resolve standard
        # OS/enterprise certificate symlinks, then validate the actual file.
        resolved_ca = absolute(os.path.realpath(ca))
        parent = files.directory(resolved_ca.parent)
        require(parent is not None, 'Invalid trusted CA bundle.')
        fd = os.open(resolved_ca.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid in (0, os.getuid())
                    and not info.st_mode & 0o022, 'Invalid trusted CA bundle.')
        finally:
            os.close(fd)
        try:
            ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cafile=str(resolved_ca))
        except ssl.SSLError:
            raise Rejected('Invalid trusted CA bundle.') from None
        share_ca = (bool(explicit_bundle)
                    or resolved_ca not in {Path(os.path.realpath(path)) for path in paths}
                    or os.environ.get('NODE_EXTRA_CA_CERTS') == str(ca))
        # Each Claude role route already names its provider. A selector in the
        # shell or in Claude's user settings env (which overrides the shell)
        # would make every other-provider role fail closed at Lumen.
        headers = [os.environ.get('ANTHROPIC_CUSTOM_HEADERS', '')]
        settings_path = os.path.join(os.environ.get('CLAUDE_CONFIG_DIR') or str(home / '.claude'), 'settings.json')
        try:
            if os.path.isfile(settings_path):
                with open(settings_path, encoding='utf-8') as handle:
                    settings = json.loads(handle.read(1024 * 1024))
                env = settings.get('env') if isinstance(settings, dict) else None
                if isinstance(env, dict) and isinstance(env.get('ANTHROPIC_CUSTOM_HEADERS'), str):
                    headers.append(env['ANTHROPIC_CUSTOM_HEADERS'])
        except (OSError, ValueError):
            pass
        require(not any(line.split(':', 1)[0].strip().lower() == 'x-lumen-provider'
                        for value in headers for line in value.splitlines()),
                'ANTHROPIC_CUSTOM_HEADERS sets X-Lumen-Provider (shell or Claude settings.json env). Claude role '
                'routes already identify their provider; remove that header, open a new terminal, and rerun setup.')
        if tty is None:
            tty = Terminal()
        api_key = tty.prompt('Lumen API key: ', secret=True)
        require(api_key and not any(ord(char) < 32 or ord(char) == 127 for char in api_key))
        models = catalog(codex, api_key, resolved_ca)
        show_models(models)
        roles = {}
        for role, protocol in (('sol', 'responses'), ('luna', 'responses'),
                               ('fable', 'messages'), ('opus', 'messages'),
                               ('sonnet', 'messages'), ('haiku', 'messages')):
            client = 'Codex ' if protocol == 'responses' else 'Claude '
            roles[role] = choose_model(tty, models, client + role.title(), protocol)
        startup = tty.prompt('Claude startup role [sonnet]: ').lower() or 'sonnet'
        require(startup in ('fable', 'opus', 'sonnet', 'haiku'), 'Invalid Claude startup role.')
        print('Desktop opt-in changes only the public model ID; the desktop provider stays unchanged.')
        answer = tty.prompt('Replace the default Codex model? [y/N]: ').lower()
        require(answer in ('', 'y', 'yes', 'n', 'no'))
        updated = codex_config(config_text, codex, {'model': roles['sol']['api_model_name']}
                               if answer in ('y', 'yes') else {})
        cli_updates = {}
        for name, path in cli_configs.items():
            selected = roles['luna' if name == 'luna' else 'sol']
            # An installer-owned provider table: profile files layer over
            # config.toml, so desktop [model_providers.lumen] headers would
            # otherwise be inherited by every CLI role request.
            settings = {'model_provider': 'lumen-cli', 'model': selected['id'],
                        'model_catalog_json': str(models_path)}
            cli_updates[path] = codex_config(cli_texts[path], codex, settings, 'lumen-cli', clear_selector=True)
        quote = shlex.quote
        block = START + '\n' + '''case "$-" in *x*) _lumen_trace=1 ;; *) _lumen_trace=0 ;; esac
case "$-" in *v*) _lumen_verbose=1 ;; *) _lumen_verbose=0 ;; esac
set +x
set +v
'''
        block += '[ ! -r ' + quote(str(key)) + ' ] || . ' + quote(str(key)) + '\n'
        for name, value in {'CODEX_HOME': str(codex_home), 'CODEX_CA_CERTIFICATE': str(ca),
                            'ANTHROPIC_BASE_URL': anthropic}.items():
            block += 'export ' + name + '=' + quote(value) + '\n'
        if share_ca:
            block += 'export NODE_EXTRA_CA_CERTS=' + quote(str(ca)) + '\n'
        block += 'unset ANTHROPIC_API_KEY LUMEN_MODEL LUMEN_CODEX_MODEL\n'
        block += 'export ANTHROPIC_AUTH_TOKEN="$LUMEN_API_KEY"\n'
        block += 'export ANTHROPIC_MODEL=' + quote(startup) + '\n'
        for role in ('fable', 'opus', 'sonnet', 'haiku'):
            row = roles[role]
            prefix = 'ANTHROPIC_DEFAULT_' + role.upper() + '_MODEL'
            # Behind an ANTHROPIC_BASE_URL gateway Claude Code honors only the
            # _NAME/_DESCRIPTION pin variables; capability pins are not exported.
            values = {'': row['id'], '_NAME': role.title() + ' — ' + row['provider_name'] + ' / ' + row['display_name'],
                      '_DESCRIPTION': row['provider'] + ' / ' + row['api_model_name']}
            for suffix, value in values.items():
                block += 'export ' + prefix + suffix + '=' + quote(value) + '\n'
        # Codex 0.160 accepts the CLI profile only for session commands and
        # --strict-config for a subset; mirror its root parser so management
        # commands (login, mcp, features, completion, ...) stay native.
        block += '''unalias codex 2>/dev/null || :
codex() (
    _lumen_state=root _lumen_command= _lumen_profile=0 _lumen_strict=0
    for _lumen_arg do
        case "$_lumen_state" in
            value) _lumen_state=root; continue ;;
            images) case "$_lumen_arg" in -?*) _lumen_state=root ;; *) continue ;; esac ;;
            debug) _lumen_command="debug $_lumen_arg"; _lumen_state=sub; continue ;;
        esac
        case "$_lumen_arg" in
            --) break ;;
            --strict-config|--strict-config=*) _lumen_strict=1; continue ;;
            -p|--profile) _lumen_profile=1; [ "$_lumen_state" != root ] || _lumen_state=value; continue ;;
            -p?*|--profile=*) _lumen_profile=1; continue ;;
        esac
        [ "$_lumen_state" = root ] || continue
        case "$_lumen_arg" in
            -i|--image) _lumen_state=images ;;
            -[cmsaC]|--config|--enable|--disable|--remote|--remote-auth-token-env|--model|--local-provider|--sandbox|--ask-for-approval|--cd|--add-dir) _lumen_state=value ;;
            -?*) ;;
            debug) _lumen_command=debug _lumen_state=debug ;;
            *) _lumen_command=$_lumen_arg _lumen_state=sub ;;
        esac
    done
    case "$_lumen_command" in
        login|logout|mcp|plugin|app-server|remote-control|app|completion|update|doctor|sandbox|execpolicy|apply|a|migrate-rollouts|cloud|cloud-tasks|responses-api-proxy|stdio-to-uds|exec-server|features|tcp-tunnel|help) ;;
        'debug prompt-input') [ "$_lumen_profile" = 1 ] || set -- --profile lumen-cli "$@" ;;
        debug|debug\\ *) ;;
        *)
            [ "$_lumen_strict" = 1 ] || set -- --strict-config "$@"
            [ "$_lumen_profile" = 1 ] || set -- --profile lumen-cli "$@" ;;
    esac
    command codex "$@"
)
'''
        block += '''if [ "$_lumen_verbose" = 1 ]; then unset _lumen_verbose; set -v; else unset _lumen_verbose; fi
if [ "$_lumen_trace" = 1 ]; then unset _lumen_trace; set -x; else unset _lumen_trace; fi
'''
        block += END + '\n'
        changes = {config: updated.encode(), models_path: codex_models(roles),
                   **{path: text.encode() for path, text in cli_updates.items()}}
        for path in profiles:
            changes[path] = profile((old[path] or b'').decode('utf-8'), block).encode()
        changes[key] = ('set +x\nset +v\nexport LUMEN_API_KEY=' + quote(api_key) + '\n').encode()
        files.install(changes, (private, codex_home), key, profiles)
        print('Lumen CLI configured. Open a new terminal (Claude Code 2.1.257+, Codex 0.160.0+):')
        print('codex  # Sol; /model lists the selected Sol/Luna targets')
        print('codex --profile lumen-luna  # Luna')
        print('claude  # ' + startup)
        print('claude --model opus  # also accepts fable, sonnet or haiku')
        print('codex login, codex mcp ... and other management commands keep native defaults.')
        for role, row in roles.items():
            print(role.title() + ' → ' + row['provider_name'] + ' / ' + row['api_model_name'])
    finally:
        if tty is not None:
            tty.close()
        files.close()


try:
    run()
except Rejected as error:
    # Rejected contains only installer-owned labels, never supplied values.
    sys.stderr.write('Lumen installation failed: ' + str(error) + '\n')
    sys.exit(1)
except BaseException:
    # Never include exception text: it may contain a supplied URL or credential.
    sys.stderr.write('Lumen installation failed; check inputs, Python 3.11+, terminal, certificates, and safe writable paths.\n')
    sys.exit(1)
LUMEN_PY
