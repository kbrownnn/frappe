# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE
# Author - Shivam Mishra <shivam@frappe.io>

import frappe
from json import loads, dumps
from frappe import _, DoesNotExistError, ValidationError, _dict
from frappe.boot import get_allowed_pages, get_allowed_reports
from frappe.core.doctype.custom_role.custom_role import get_custom_allowed_roles
from functools import wraps
from frappe.cache_manager import (
	build_domain_restriced_doctype_cache,
	build_domain_restriced_page_cache,
	build_table_count_cache
)

def handle_not_exist(fn):
	@wraps(fn)
	def wrapper(*args, **kwargs):
		try:
			return fn(*args, **kwargs)
		except DoesNotExistError:
			if frappe.message_log:
				frappe.message_log.pop()
			return []

	return wrapper


class Workspace:
	def __init__(self, page, minimal=False):
		self.page_name = page.get('name')
		self.page_title = page.get('title')
		self.public_page = page.get('public')
		self.extended_links = []
		self.extended_charts = []
		self.extended_shortcuts = []
		self.workspace_manager = "Workspace Manager" in frappe.get_roles()

		self.user = frappe.get_user()
		self.allowed_modules = self.get_cached('user_allowed_modules', self.get_allowed_modules)

		self.doc = frappe.get_cached_doc("Workspace", self.page_name)

		if self.doc and self.doc.module and self.doc.module not in self.allowed_modules and not self.workspace_manager:
			raise frappe.PermissionError

		self.can_read = self.get_cached('user_perm_can_read', self.get_can_read_items)

		self.allowed_pages = get_allowed_pages(cache=True)
		self.allowed_reports = get_allowed_reports(cache=True)

		if not minimal:
			if self.doc.content:
				self.onboarding_list = [x['data']['onboarding_name'] for x in loads(self.doc.content) if x['type'] == 'onboarding']
			self.onboardings = []

			self.table_counts = get_table_with_counts()
		self.restricted_doctypes = frappe.cache().get_value("domain_restricted_doctypes") or build_domain_restriced_doctype_cache()
		self.restricted_pages = frappe.cache().get_value("domain_restricted_pages") or build_domain_restriced_page_cache()

	def is_page_allowed(self):
		cards = self.doc.get_link_groups() + get_custom_reports_and_doctypes(self.doc.module)
		shortcuts = self.doc.shortcuts

		for section in cards:
			links = loads(section.get('links')) if isinstance(section.get('links'), str) else section.get('links')
			for item in links:
				if self.is_item_allowed(item.get('link_to'), item.get('link_type')):
					return True

		def _in_active_domains(item):
			if not item.restrict_to_domain:
				return True
			else:
				return item.restrict_to_domain in frappe.get_active_domains()

		for item in shortcuts:
			if self.is_item_allowed(item.link_to, item.type) and _in_active_domains(item):
				return True

		if not shortcuts and not self.doc.links:
			return True

		return False

	def is_permitted(self):
		"""Returns true if Has Role is not set or the user is allowed."""
		from frappe.utils import has_common

		allowed = [d.role for d in frappe.get_all("Has Role", fields=["role"], filters={"parent": self.doc.name})]

		custom_roles = get_custom_allowed_roles('page', self.doc.name)
		allowed.extend(custom_roles)

		if not allowed:
			return True

		roles = frappe.get_roles()

		if has_common(roles, allowed):
			return True

	def get_cached(self, cache_key, fallback_fn):
		_cache = frappe.cache()

		value = _cache.get_value(cache_key, user=frappe.session.user)
		if value:
			return value

		value = fallback_fn()

		# Expire every six hour
		_cache.set_value(cache_key, value, frappe.session.user, 21600)
		return value

	def get_can_read_items(self):
		if not self.user.can_read:
			self.user.build_permissions()

		return self.user.can_read

	def get_allowed_modules(self):
		if not self.user.allow_modules:
			self.user.build_permissions()

		return self.user.allow_modules

	def get_onboarding_doc(self, onboarding):
		# Check if onboarding is enabled
		if not frappe.get_system_settings("enable_onboarding"):
			return None

		if not self.onboarding_list:
			return None

		if frappe.db.get_value("Module Onboarding", onboarding, "is_complete"):
			return None

		doc = frappe.get_doc("Module Onboarding", onboarding)

		# Check if user is allowed
		allowed_roles = set(doc.get_allowed_roles())
		user_roles = set(frappe.get_roles())
		if not allowed_roles & user_roles:
			return None

		# Check if already complete
		if doc.check_completion():
			return None

		return doc

	def get_pages_to_extend(self):
		pages = frappe.get_all("Workspace", filters={
			"extends": self.page_name,
			'restrict_to_domain': ['in', frappe.get_active_domains()],
			'for_user': '',
			'module': ['in', self.allowed_modules]
		})

		pages = [frappe.get_cached_doc("Workspace", page['name']) for page in pages]

		for page in pages:
			self.extended_links = self.extended_links + page.get_link_groups()
			self.extended_charts = self.extended_charts + page.charts
			self.extended_shortcuts = self.extended_shortcuts + page.shortcuts

	def is_item_allowed(self, name, item_type):
		if frappe.session.user == "Administrator":
			return True

		item_type = item_type.lower()

		if item_type == "doctype":
			return (name in self.can_read or [] and name in self.restricted_doctypes or [])
		if item_type == "page":
			return (name in self.allowed_pages and name in self.restricted_pages)
		if item_type == "report":
			return name in self.allowed_reports
		if item_type == "help":
			return True
		if item_type == "dashboard":
			return True

		return False

	def build_workspace(self):
		self.cards = {
			'label': _(self.doc.cards_label),
			'items': self.get_links()
		}

		self.charts = {
			'label': _(self.doc.charts_label),
			'items': self.get_charts()
		}

		self.shortcuts = {
			'label': _(self.doc.shortcuts_label),
			'items': self.get_shortcuts()
		}

		self.onboardings = {
			'items': self.get_onboardings()
		}

	def _doctype_contains_a_record(self, name):
		exists = self.table_counts.get(name, False)

		if not exists and frappe.db.exists(name):
			if not frappe.db.get_value('DocType', name, 'issingle'):
				exists = bool(frappe.db.get_all(name, limit=1))
			else:
				exists = True
			self.table_counts[name] = exists

		return exists

	def _prepare_item(self, item):
		if item.dependencies:

			dependencies = [dep.strip() for dep in item.dependencies.split(",")]

			incomplete_dependencies = [d for d in dependencies if not self._doctype_contains_a_record(d)]

			if len(incomplete_dependencies):
				item.incomplete_dependencies = incomplete_dependencies
			else:
				item.incomplete_dependencies = ""

		if item.onboard:
			# Mark Spotlights for initial
			if item.get("type") == "doctype":
				name = item.get("name")
				count = self._doctype_contains_a_record(name)

				item["count"] = count

		# Translate label
		item["label"] = _(item.label) if item.label else _(item.name)

		return item

	@handle_not_exist
	def get_links(self):
		cards = self.doc.get_link_groups()

		if not self.doc.hide_custom:
			cards = cards + get_custom_reports_and_doctypes(self.doc.module)

		if len(self.extended_links):
			cards = merge_cards_based_on_label(cards + self.extended_links)

		default_country = frappe.db.get_default("country")

		new_data = []
		for card in cards:
			new_items = []
			card = _dict(card)

			links = card.get('links', [])

			for item in links:
				item = _dict(item)

				# Condition: based on country
				if item.country and item.country != default_country:
					continue

				# Check if user is allowed to view
				if self.is_item_allowed(item.link_to, item.link_type):
					prepared_item = self._prepare_item(item)
					new_items.append(prepared_item)

			if new_items:
				if isinstance(card, _dict):
					new_card = card.copy()
				else:
					new_card = card.as_dict().copy()
				new_card["links"] = new_items
				new_card["label"] = _(new_card["label"])
				new_data.append(new_card)

		return new_data

	@handle_not_exist
	def get_charts(self):
		all_charts = []
		if frappe.has_permission("Dashboard Chart", throw=False):
			charts = self.doc.charts
			if len(self.extended_charts):
				charts = charts + self.extended_charts

			for chart in charts:
				if frappe.has_permission('Dashboard Chart', doc=chart.chart_name):
					# Translate label
					chart.label = _(chart.label) if chart.label else _(chart.chart_name)
					all_charts.append(chart)

		return all_charts

	@handle_not_exist
	def get_shortcuts(self):

		def _in_active_domains(item):
			if not item.restrict_to_domain:
				return True
			else:
				return item.restrict_to_domain in frappe.get_active_domains()

		items = []
		shortcuts = self.doc.shortcuts
		if len(self.extended_shortcuts):
			shortcuts = shortcuts + self.extended_shortcuts

		for item in shortcuts:
			new_item = item.as_dict().copy()
			if self.is_item_allowed(item.link_to, item.type) and _in_active_domains(item):
				if item.type == "Report":
					report = self.allowed_reports.get(item.link_to, {})
					if report.get("report_type") in ["Query Report", "Script Report", "Custom Report"]:
						new_item['is_query_report'] = 1
					else:
						new_item['ref_doctype'] = report.get('ref_doctype')

				# Translate label
				new_item["label"] = _(item.label) if item.label else _(item.link_to)

				items.append(new_item)

		return items

	@handle_not_exist
	def get_onboardings(self):
		if self.onboarding_list:
			for onboarding in self.onboarding_list:
				onboarding_doc = self.get_onboarding_doc(onboarding)
				if onboarding_doc:
					item = {
						'label':  _(onboarding),
						'title': _(onboarding_doc.title),
						'subtitle': _(onboarding_doc.subtitle),
						'success': _(onboarding_doc.success_message),
						'docs_url': onboarding_doc.documentation_url,
						'items': self.get_onboarding_steps(onboarding_doc)
					}
					self.onboardings.append(item)
		return self.onboardings

	@handle_not_exist
	def get_onboarding_steps(self, onboarding_doc):
		steps = []
		for doc in onboarding_doc.get_steps():
			step = doc.as_dict().copy()
			step.label = _(doc.title)
			if step.action == "Create Entry":
				step.is_submittable = frappe.db.get_value("DocType", step.reference_document, 'is_submittable', cache=True)
			steps.append(step)

		return steps


@frappe.whitelist()
@frappe.read_only()
def get_desktop_page(page):
	"""Applies permissions, customizations and returns the configruration for a page
	on desk.

	Args:
		page (json): page data

	Returns:
		dict: dictionary of cards, charts and shortcuts to be displayed on website
	"""
	try:
		wspace = Workspace(loads(page))
		wspace.build_workspace()
		return {
			'charts': wspace.charts,
			'shortcuts': wspace.shortcuts,
			'cards': wspace.cards,
			'onboardings': wspace.onboardings,
			'allow_customization': not wspace.doc.disable_user_customization
		}
	except DoesNotExistError:
		frappe.log_error(frappe.get_traceback())
		return {}

@frappe.whitelist()
def get_wspace_sidebar_items():
	"""Get list of sidebar items for desk"""
	has_access = "Workspace Manager" in frappe.get_roles()

	# don't get domain restricted pages
	blocked_modules = frappe.get_doc('User', frappe.session.user).get_blocked_modules()
	blocked_modules.append('Dummy Module')

	filters = {
		'restrict_to_domain': ['in', frappe.get_active_domains()],
		'module': ['not in', blocked_modules]
	}

	if has_access:
		filters = []

	# pages sorted based on sequence id
	order_by = "sequence_id asc"
	fields = ["name", "title", "for_user", "parent_page", "content", "public",  "module", "icon"]
	all_pages = frappe.get_all("Workspace", fields=fields, filters=filters, order_by=order_by, ignore_permissions=True)
	pages = []
	private_pages = []

	# Filter Page based on Permission
	for page in all_pages:
		try:
			wspace = Workspace(page)
			if wspace.is_permitted() and wspace.is_page_allowed() or has_access:
				if page.public:
					pages.append(page)
				elif page.for_user == frappe.session.user:
					private_pages.append(page)
				page['label'] = _(page.get('name'))
		except frappe.PermissionError:
			pass
	if private_pages:
		pages.extend(private_pages)

	return {'pages': pages, 'has_access': has_access}

def get_table_with_counts():
	counts = frappe.cache().get_value("information_schema:counts")
	if not counts:
		counts = build_table_count_cache()

	return counts

def get_custom_reports_and_doctypes(module):
	return [
		_dict({
			"label": _("Custom Documents"),
			"links": get_custom_doctype_list(module)
		}),
		_dict({
			"label": _("Custom Reports"),
			"links": get_custom_report_list(module)
		}),
	]

def get_custom_doctype_list(module):
	doctypes =  frappe.get_all("DocType", fields=["name"], filters={"custom": 1, "istable": 0, "module": module}, order_by="name")

	out = []
	for d in doctypes:
		out.append({
			"type": "Link",
			"link_type": "doctype",
			"link_to": d.name,
			"label": _(d.name)
		})

	return out


def get_custom_report_list(module):
	"""Returns list on new style reports for modules."""
	reports =  frappe.get_all("Report", fields=["name", "ref_doctype", "report_type"], filters=
		{"is_standard": "No", "disabled": 0, "module": module},
		order_by="name")

	out = []
	for r in reports:
		out.append({
			"type": "Link",
			"link_type": "report",
			"doctype": r.ref_doctype,
			"dependencies": r.ref_doctype,
			"is_query_report": 1 if r.report_type in ("Query Report", "Script Report", "Custom Report") else 0,
			"label": _(r.name),
			"link_to": r.name,
		})

	return out

def get_custom_workspace_for_user(page):
	"""Get custom page from workspace if exists or create one

	Args:
		page (stirng): Page name

	Returns:
		Object: Document object
	"""
	filters = {
		'extends': page,
		'for_user': frappe.session.user,
	}
	pages = frappe.get_list("Workspace", filters=filters)
	if pages:
		return frappe.get_doc("Workspace", pages[0])
	doc = frappe.new_doc("Workspace")
	doc.extends = page
	doc.for_user = frappe.session.user
	return doc

@frappe.whitelist()
def save_customization(page, config):
	"""Save customizations as a separate doctype in Workspace per user

	Args:
		page (string): Name of the page to be edited
		config (dict): Dictionary config of al widgets

	Returns:
		Boolean: Customization saving status
	"""
	original_page = frappe.get_doc("Workspace", page)
	page_doc = get_custom_workspace_for_user(page)

	# Update field values
	page_doc.update({
		"icon": original_page.icon,
		"charts_label": original_page.charts_label,
		"cards_label": original_page.cards_label,
		"shortcuts_label": original_page.shortcuts_label,
		"module": original_page.module,
		"onboarding": original_page.onboarding,
		"developer_mode_only": original_page.developer_mode_only,
		"category": original_page.category
	})

	config = _dict(loads(config))
	if config.charts:
		page_doc.charts = prepare_widget(config.charts, "Workspace Chart", "charts")
	if config.shortcuts:
		page_doc.shortcuts = prepare_widget(config.shortcuts, "Workspace Shortcut", "shortcuts")
	if config.cards:
		page_doc.build_links_table_from_cards(config.cards)

	# Set label
	page_doc.label = page + '-' + frappe.session.user

	try:
		if page_doc.is_new():
			page_doc.insert(ignore_permissions=True)
		else:
			page_doc.save(ignore_permissions=True)
	except (ValidationError, TypeError) as e:
		# Create a json string to log
		json_config = dumps(config, sort_keys=True, indent=4)

		# Error log body
		log = \
			"""
		page: {0}
		config: {1}
		exception: {2}
		""".format(page, json_config, e)
		frappe.log_error(log, _("Could not save customization"))
		return False

	return True

def save_new_widget(doc, page, blocks, new_widgets):

	widgets = _dict(loads(new_widgets))

	if widgets.chart:
		doc.charts.extend(new_widget(widgets.chart, "Workspace Chart", "charts"))
	if widgets.shortcut:
		doc.shortcuts.extend(new_widget(widgets.shortcut, "Workspace Shortcut", "shortcuts"))
	if widgets.card:
		doc.build_links_table_from_card(widgets.card)

	# remove duplicate and unwanted widgets
	if widgets:
		clean_up(doc, blocks)

	try:
		doc.save(ignore_permissions=True)
	except (ValidationError, TypeError) as e:
		# Create a json string to log
		json_config = dumps(widgets, sort_keys=True, indent=4)

		# Error log body
		log = \
			"""
		page: {0}
		config: {1}
		exception: {2}
		""".format(page, json_config, e)
		frappe.log_error(log, _("Could not save customization"))
		return False

	return True
def clean_up(original_page, blocks):
	page_widgets = {}

	for wid in ['shortcut', 'card', 'chart']:
		# get list of widget's name from blocks
		page_widgets[wid] = [x['data'][wid + '_name'] for x in loads(blocks) if x['type'] == wid]

	# shortcut & chart cleanup
	for wid in ['shortcut', 'chart']:
		updated_widgets = []
		original_page.get(wid+'s').reverse()

		for w in original_page.get(wid+'s'):
			if w.label in page_widgets[wid] and w.label not in [x.label for x in updated_widgets]:
				updated_widgets.append(w)
		original_page.set(wid+'s', updated_widgets)

	# card cleanup
	for i, v in enumerate(original_page.links):
		if v.type == 'Card Break' and v.label not in page_widgets['card']:
			del original_page.links[i : i+v.link_count+1]

def new_widget(config, doctype, parentfield):
	if not config:
		return []
	prepare_widget_list = []
	for idx, widget in enumerate(config):
		# Some cleanup
		widget.pop("name", None)

		# New Doc
		doc = frappe.new_doc(doctype)
		doc.update(widget)

		# Manually Set IDX
		doc.idx = idx + 1

		# Set Parent Field
		doc.parentfield = parentfield

		prepare_widget_list.append(doc)
	return prepare_widget_list

def prepare_widget(config, doctype, parentfield):
	"""Create widget child table entries with parent details

	Args:
		config (dict): Dictionary containing widget config
		doctype (string): Doctype name of the child table
		parentfield (string): Parent field for the child table

	Returns:
		TYPE: List of Document objects
	"""
	if not config:
		return []
	order = config.get('order')
	widgets = config.get('widgets')
	prepare_widget_list = []
	for idx, name in enumerate(order):
		wid_config = widgets[name].copy()
		# Some cleanup
		wid_config.pop("name", None)

		# New Doc
		doc = frappe.new_doc(doctype)
		doc.update(wid_config)

		# Manually Set IDX
		doc.idx = idx + 1

		# Set Parent Field
		doc.parentfield = parentfield

		prepare_widget_list.append(doc)
	return prepare_widget_list


@frappe.whitelist()
def update_onboarding_step(name, field, value):
	"""Update status of onboaridng step

	Args:
	    name (string): Name of the doc
	    field (string): field to be updated
	    value: Value to be updated

	"""
	frappe.db.set_value("Onboarding Step", name, field, value)

@frappe.whitelist()
def reset_customization(page):
	"""Reset workspace customizations for a user

	Args:
		page (string): Name of the page to be reset
	"""
	page_doc = get_custom_workspace_for_user(page)
	page_doc.delete()

def merge_cards_based_on_label(cards):
	"""Merge cards with common label."""
	cards_dict = {}
	for card in cards:
		label = card.get('label')
		if label in cards_dict:
			links = cards_dict[label].links + card.links
			cards_dict[label].update(dict(links=links))
			cards_dict[label] = cards_dict.pop(label)
		else:
			cards_dict[label] = card

	return list(cards_dict.values())

