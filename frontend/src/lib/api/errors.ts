export class ApiError extends Error {
	status: number;
	/** Stable JSON `code`, including known signup-approval codes returned as HTTP 403 `detail`. */
	code?: string;

	constructor(status: number, message: string, code?: string, public linkTicket?: { link_token: string; domain_id: string }) {
		super(message);
		this.status = status;
		this.code = code;
	}
}
