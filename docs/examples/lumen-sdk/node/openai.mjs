import { writeFile } from 'node:fs/promises';
import OpenAI from 'openai';
import { required } from './env.mjs';

const client = new OpenAI({
  apiKey: required('LUMEN_API_KEY'),
  baseURL: `${required('LUMEN_BASE_URL').replace(/\/+$/, '')}/v1`,
  maxRetries: 0,
});
const prompt = 'Explain what an API gateway does in one sentence.';
const messages = [{ role: 'user', content: prompt }];
const operation = process.argv[2];

switch (operation) {
  case 'list':
    for await (const model of client.models.list()) console.log(model.id);
    break;
  case 'chat': {
    const result = await client.chat.completions.create({ model: required('LUMEN_OPENAI_MODEL'), messages });
    console.log(result.choices[0].message.content);
    break;
  }
  case 'responses': {
    const result = await client.responses.create({ model: required('LUMEN_OPENAI_MODEL'), input: prompt });
    console.log(result.output_text);
    break;
  }
  case 'stream': {
    const stream = await client.chat.completions.create({ model: required('LUMEN_OPENAI_MODEL'), messages, stream: true });
    for await (const chunk of stream) process.stdout.write(chunk.choices[0]?.delta.content ?? '');
    console.log();
    break;
  }
  case 'embed': {
    const result = await client.embeddings.create({ model: required('LUMEN_OPENAI_EMBED_MODEL'), input: prompt });
    console.log('Embedding dimensions:', result.data[0].embedding.length);
    break;
  }
  case 'image': {
    const result = await client.images.generate({ model: required('LUMEN_IMAGE_MODEL'), prompt: 'A paper boat on still water', n: 1 });
    const image = result.data?.[0]?.b64_json;
    if (!image) throw new Error('Lumen did not return an image');
    await writeFile('lumen-node-image.png', Buffer.from(image, 'base64'), { flag: 'wx' });
    console.log('Saved lumen-node-image.png');
    break;
  }
  case 'providers':
    for (const family of ['CLAUDE', 'GEMINI', 'PERPLEXITY']) {
      const provider = required(`LUMEN_${family}_PROVIDER`);
      const result = await client.chat.completions.create(
        { model: required(`LUMEN_${family}_MODEL`), messages },
        { headers: { 'X-Lumen-Provider': provider } },
      );
      console.log(`${provider}: ${result.choices[0].message.content}`);
    }
    break;
  default:
    throw new Error('Choose list, chat, responses, stream, embed, image, or providers');
}
