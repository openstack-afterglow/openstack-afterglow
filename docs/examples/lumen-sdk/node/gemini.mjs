import { GoogleGenAI } from '@google/genai';
import { required } from './env.mjs';

const client = new GoogleGenAI({
  apiKey: required('LUMEN_API_KEY'),
  vertexai: false,
  httpOptions: { baseUrl: required('LUMEN_BASE_URL').replace(/\/+$/, ''), apiVersion: 'v1beta' },
});
const operation = process.argv[2];
const contents = 'Explain what an API gateway does in one sentence.';
if (operation === 'list') {
  for await (const model of await client.models.list({})) console.log(model.name, model.supportedActions?.join(', ') ?? '');
} else if (operation === 'embed') {
  const result = await client.models.embedContent({ model: required('LUMEN_GEMINI_EMBED_MODEL'), contents });
  console.log('Embedding dimensions:', result.embeddings[0].values.length);
} else if (operation === 'generate' || operation === 'stream') {
  const provider = process.env.LUMEN_GEMINI_PROVIDER;
  const config = provider ? { httpOptions: { headers: { 'X-Lumen-Provider': provider } } } : undefined;
  const request = { model: required('LUMEN_GEMINI_MODEL'), contents, config };
  if (operation === 'generate') {
    const result = await client.models.generateContent(request);
    console.log(result.text);
  } else {
    const stream = await client.models.generateContentStream(request);
    for await (const chunk of stream) process.stdout.write(chunk.text ?? '');
    console.log();
  }
} else {
  throw new Error('Choose list, generate, stream, or embed');
}
