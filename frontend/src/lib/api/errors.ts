export class ApiError extends Error {
	status: number;
	/** Stable machine-readable error code from a JSON `code` field, when the endpoint provides one. */
	code?: string;

	constructor(status: number, message: string, code?: string) {
		super(message);
		this.status = status;
		this.code = code;
	}
}
