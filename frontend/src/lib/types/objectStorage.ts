export interface SwiftContainer {
  name: string;
  count: number;
  bytes: number;
}

export interface AccountMeta {
  container_count: number;
  object_count: number;
  bytes_used: number;
}
export interface SwiftObject {
  name: string;
  bytes: number;
  content_type: string;
  last_modified: string;
  etag: string;
  is_dir?: boolean;
}

export interface SwiftObjectMeta extends SwiftObject {
  container: string;
  content_encoding?: string;
  content_disposition?: string;
  delete_at?: string;
  sha256?: string;
  detected_content_type?: string;
}

/** 백엔드 thumbnail 엔드포인트가 렌더링할 수 있는 형식. */
export const THUMBNAILABLE_TYPES: ReadonlySet<string> = new Set([
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
  'image/bmp',
  'image/tiff',
  'application/pdf'
]);

/** 백엔드 thumbnails.MAX_SOURCE_BYTES 와 같은 상한. */
export const THUMBNAIL_MAX_SOURCE_BYTES = 64 * 1024 * 1024;
