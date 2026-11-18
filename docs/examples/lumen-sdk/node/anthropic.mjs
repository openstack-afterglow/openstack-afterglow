import Anthropic from '@anthropic-ai/sdk';
import { required } from './env.mjs';

const client = new Anthropic({
  apiKey: required('LUMEN_API_KEY'),
  baseURL: required('LUMEN_BASE_URL').replace(/\/+$/, ''),
  maxRetries: 0,
});
const operation = process.argv[2];
if (operation === 'list') {
  for await (const model of client.models.list()) console.log(model.id);
} else if (operation === 'message' || operation === 'stream') {
  const body = {
    model: required('LUMEN_CLAUDE_MODEL'),
    max_tokens: 256,
    messages: [{ role: 'user', content: 'Explain what an API gateway does in one sentence.' }],
  };
  const provider = process.env.LUMEN_CLAUDE_PROVIDER;
  const options = provider ? { headers: { 'X-Lumen-Provider': provider } } : undefined;
  if (operation === 'message') {
    const message = await client.messages.create(body, options);
    for (const block of message.content) if (block.type === 'text') console.log(block.text);
  } else {
    const stream = client.messages.stream(body, options);
    for await (const event of stream) {
      if (event.type === 'content_block_delta' && event.delta.type === 'text_delta') process.stdout.write(event.delta.text);
    }
    console.log();
  }
} else {
  throw new Error('Choose list, message, or stream');
}
