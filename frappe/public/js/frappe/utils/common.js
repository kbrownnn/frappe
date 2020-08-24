// common file between desk and website

frappe.avatar = function (user, css_class, title, image_url=null, remove_avatar=false) {
	let user_info;
	if (user) {
		// desk
		user_info = frappe.user_info(user);
	} else {
		// website
		let full_name = title || frappe.get_cookie("full_name");
		user_info = {
			image: image_url === null ? frappe.get_cookie("user_image") : image_url,
			fullname: full_name,
			abbr: frappe.get_abbr(full_name),
			color: frappe.get_palette(full_name)
		};
	}

	if (!title) {
		title = user_info.fullname;
	}

	if (!css_class) {
		css_class = "avatar-small";
	}

	if (user_info.image || image_url) {
		image_url = image_url || user_info.image;

		const image = (window.cordova && image_url.indexOf('http') === -1) ? frappe.base_url + image_url : image_url;

		return `<span class="avatar ${css_class}" title="${title}">
				<span class="avatar-frame" style='background-image: url("${image}")'
					title="${title}"></span>
			</span>`;
	} else {
		var abbr = user_info.abbr;
		if (css_class === 'avatar-small' || css_class == 'avatar-xs') {
			abbr = abbr.substr(0, 1);
		}
		return `<span class="avatar ${css_class}" title="${title}">
			<div class="avatar-frame standard-image"
				style="background-color: var(${user_info.color[0]}); color: var(${user_info.color[1]})">
					${abbr}
			</div>
		</span>`;
	}
};

frappe.avatar_group = function(users, limit=4, options={}) {
	let icon_html = '';
	const display_users = users.slice(0, limit);
	const extra_users = users.slice(limit);

	let html = display_users.map(user => frappe.avatar(user, 'avatar-small ' + options.css_class)).join('');
	if (extra_users.length === 1) {
		html += frappe.avatar(extra_users[0], 'avatar-small ' + options.css_class);
	} else if (extra_users.length > 1) {
		html = `
			<span class="avatar avatar-small ${options.css_class}">
				<div class="avatar-frame standard-image avatar-extra-count"
					title="${extra_users.map(u => frappe.user_info(u).fullname).join(', ')}">
					+${extra_users.length}
				</div>
			</span>
			${html}
		`;
	}

	if (options.action_icon) {
		icon_html = `<span class="avatar-action">
			${frappe.utils.icon(options.action_icon, 'md')}
		</span>`;
	}

	const $avatar_group =
		$(`<div class="avatar-group ${options.align || 'right'} ${options.overlap != false ? 'overlap': ''}">
			${icon_html}
			${html}
		</div>`);

	$avatar_group.find('.avatar-action').on('click', options.action);
	return $avatar_group;
};

frappe.ui.scroll = function(element, animate, additional_offset) {
	var header_offset = $(".navbar").height() + $(".page-head").height();
	var top = $(element).offset().top - header_offset - cint(additional_offset);
	if (animate) {
		$("html, body").animate({ scrollTop: top });
	} else {
		$(window).scrollTop(top);
	}
};

frappe.palette = [
	['--orange-100', '--orange-600'],
	['--pink-50', '--pink-500'],
	['--blue-50', '--blue-500'],
	['--green-50', '--green-500'],
	['--dark-green-50', '--dark-green-500'],
	['--red-50', '--red-500'],
	['--yellow-50', '--yellow-500'],
	['--purple-50', '--purple-500'],
	['--gray-50', '--gray-500']
]

frappe.get_palette = function(txt) {
	var idx = cint((parseInt(md5(txt).substr(4,2), 16) + 1) / 5.33);
	return frappe.palette[idx%8];
}

frappe.get_abbr = function(txt, max_length) {
	if (!txt) return "";
	var abbr = "";
	$.each(txt.split(" "), function(i, w) {
		if (abbr.length >= (max_length || 2)) {
			// break
			return false;

		} else if (!w.trim().length) {
			// continue
			return true;
		}
		abbr += w.trim()[0];
	});

	return abbr || "?";
}

frappe.gravatars = {};
frappe.get_gravatar = function(email_id, size = 0) {
	var param = size ? ('s=' + size) : 'd=retro';
	if(!frappe.gravatars[email_id]) {
		// TODO: check if gravatar exists
		frappe.gravatars[email_id] = "https://secure.gravatar.com/avatar/" + md5(email_id) + "?" + param;
	}
	return frappe.gravatars[email_id];
}

// string commons

window.repl =function repl(s, dict) {
	if(s==null)return '';
	for(var key in dict) {
		s = s.split("%("+key+")s").join(dict[key]);
	}
	return s;
}

window.replace_all = function(s, t1, t2) {
	return s.split(t1).join(t2);
}

window.strip_html = function(txt) {
	return txt.replace(/<[^>]*>/g, "");
}

window.strip = function(s, chars) {
	if (s) {
		var s= lstrip(s, chars)
		s = rstrip(s, chars);
		return s;
	}
}

window.lstrip = function lstrip(s, chars) {
	if(!chars) chars = ['\n', '\t', ' '];
	// strip left
	var first_char = s.substr(0,1);
	while(in_list(chars, first_char)) {
		var s = s.substr(1);
		first_char = s.substr(0,1);
	}
	return s;
}

window.rstrip = function(s, chars) {
	if(!chars) chars = ['\n', '\t', ' '];
	var last_char = s.substr(s.length-1);
	while(in_list(chars, last_char)) {
		var s = s.substr(0, s.length-1);
		last_char = s.substr(s.length-1);
	}
	return s;
}

frappe.get_cookie = function getCookie(name) {
	return frappe.get_cookies()[name];
}

frappe.get_cookies = function getCookies() {
	var c = document.cookie, v = 0, cookies = {};
	if (document.cookie.match(/^\s*\$Version=(?:"1"|1);\s*(.*)/)) {
		c = RegExp.$1;
		v = 1;
	}
	if (v === 0) {
		c.split(/[,;]/).map(function(cookie) {
			var parts = cookie.split(/=/, 2),
				name = decodeURIComponent(parts[0].trimLeft()),
				value = parts.length > 1 ? decodeURIComponent(parts[1].trimRight()) : null;
			if(value && value.charAt(0)==='"') {
				value = value.substr(1, value.length-2);
			}
			cookies[name] = value;
		});
	} else {
		c.match(/(?:^|\s+)([!#$%&'*+\-.0-9A-Z^`a-z|~]+)=([!#$%&'*+\-.0-9A-Z^`a-z|~]*|"(?:[\x20-\x7E\x80\xFF]|\\[\x00-\x7F])*")(?=\s*[,;]|$)/g).map(function($0, $1) {
			var name = $0,
				value = $1.charAt(0) === '"'
						? $1.substr(1, -1).replace(/\\(.)/g, "$1")
						: $1;
			cookies[name] = value;
		});
	}
	return cookies;
}

frappe.is_mobile = function() {
	return $(document).width() < 768;
}

frappe.utils.xss_sanitise = function (string, options) {
	// Reference - https://www.owasp.org/index.php/XSS_(Cross_Site_Scripting)_Prevention_Cheat_Sheet
	let sanitised = string; // un-sanitised string.
	const DEFAULT_OPTIONS = {
		strategies: ['html', 'js'] // use all strategies.
	}
	const HTML_ESCAPE_MAP = {
		'<': '&lt',
		'>': '&gt',
		'"': '&quot',
		"'": '&#x27',
		'/': '&#x2F'
	};
	const REGEX_SCRIPT     = /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi; // used in jQuery 1.7.2 src/ajax.js Line 14
	options          	   = Object.assign({ }, DEFAULT_OPTIONS, options); // don't deep copy, immutable beauty.

	// Rule 1
	if ( options.strategies.includes('html') ) {
		for (let char in HTML_ESCAPE_MAP) {
			const escape = HTML_ESCAPE_MAP[char];
			const regex = new RegExp(char, "g");
			sanitised = sanitised.replace(regex, escape);
		}
	}

	// Rule 3 - TODO: Check event handlers?
	if ( options.strategies.includes('js') ) {
		sanitised = sanitised.replace(REGEX_SCRIPT, "");
	}

	return sanitised;
}

frappe.utils.sanitise_redirect = (url) => {
	const is_external = (() => {
		return (url) => {
			function domain(url) {
				let base_domain = /^(?:https?:\/\/)?(?:[^@\n]+@)?(?:www\.)?([^:/\n?]+)/img.exec(url);
				return base_domain == null ? "" : base_domain[1];
			}

			function is_absolute(url) {
				// returns true for url that have a defined scheme
				// anything else, eg. internal urls return false
				return /^(?:[a-z]+:)?\/\//i.test(url);
			}

			// check for base domain only if the url is absolute
			// return true for relative url (except protocol-relative urls)
			return is_absolute(url) ? domain(location.href) !== domain(url) : false;
		}
	})();

	const sanitise_javascript = ((url) => {
		// please do not ask how or why
		const REGEX_SCRIPT = /j[\s]*(&#x.{1,7})?a[\s]*(&#x.{1,7})?v[\s]*(&#x.{1,7})?a[\s]*(&#x.{1,7})?s[\s]*(&#x.{1,7})?c[\s]*(&#x.{1,7})?r[\s]*(&#x.{1,7})?i[\s]*(&#x.{1,7})?p[\s]*(&#x.{1,7})?t/gi;

		return url.replace(REGEX_SCRIPT, "");
	});

	url = frappe.utils.strip_url(url);

	return is_external(url) ? "" : sanitise_javascript(frappe.utils.xss_sanitise(url, {strategies: ["js"]}));
};

frappe.utils.strip_url = (url) => {
	// strips invalid characters from the beginning of the URL
	// in our case, the url can start with either a protocol, //, or even #
	// so anything except those characters can be considered invalid
	return url.replace(/^[^A-Za-z0-9(//)#]+/g, '');
}

frappe.utils.new_auto_repeat_prompt = function(frm) {
	const fields = [
		{
			'fieldname': 'frequency',
			'fieldtype': 'Select',
			'label': __('Frequency'),
			'reqd': 1,
			'options': [
				{'label': __('Daily'), 'value': 'Daily'},
				{'label': __('Weekly'), 'value': 'Weekly'},
				{'label': __('Monthly'), 'value': 'Monthly'},
				{'label': __('Quarterly'), 'value': 'Quarterly'},
				{'label': __('Half-yearly'), 'value': 'Half-yearly'},
				{'label': __('Yearly'), 'value': 'Yearly'}
			]
		},
		{
			'fieldname': 'start_date',
			'fieldtype': 'Date',
			'label': __('Start Date'),
			'reqd': 1,
			'default': frappe.datetime.nowdate()
		},
		{
			'fieldname': 'end_date',
			'fieldtype': 'Date',
			'label': __('End Date')
		}
	];
	frappe.prompt(fields, function(values) {
		frappe.call({
			method: "frappe.automation.doctype.auto_repeat.auto_repeat.make_auto_repeat",
			args: {
				'doctype': frm.doc.doctype,
				'docname': frm.doc.name,
				'frequency': values['frequency'],
				'start_date': values['start_date'],
				'end_date': values['end_date']
			},
			callback: function (r) {
				if (r.message) {
					frappe.show_alert({
						'message': __("Auto Repeat created for this document"),
						'indicator': 'green'
					});
					frm.reload_doc();
				}
			}
		});
	},
	__('Auto Repeat'),
	__('Save')
	);
}

frappe.utils.get_page_view_count = function(route) {
	return frappe.call("frappe.website.doctype.web_page_view.web_page_view.get_page_view_count", {
		path: route
	});
};