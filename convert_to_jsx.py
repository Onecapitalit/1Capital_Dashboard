import re

with open('SalesDashboard/core/templates/website.html', 'r') as f:
    content = f.read()

body_match = re.search(r'<body>(.*?)<script>', content, re.DOTALL)
if not body_match:
    print("Could not find body")
    exit(1)
html = body_match.group(1)

# Basic replacements
html = html.replace('class=', 'className=')
html = html.replace('for=', 'htmlFor=')

# Convert simple styles
def style_replacer(match):
    style_str = match.group(1)
    # This is a very basic parse, might not cover all edge cases but we'll see
    rules = style_str.split(';')
    out_rules = []
    for r in rules:
        if ':' in r:
            k, v = r.split(':', 1)
            k = k.strip()
            # camelCase
            k = re.sub(r'-([a-z])', lambda m: m.group(1).upper(), k)
            v = v.strip().replace("'", '"')
            out_rules.append(f"'{k}': '{v}'")
    return "style={{" + ", ".join(out_rules) + "}}"

html = re.sub(r'style="(.*?)"', style_replacer, html)

# Close tags
html = re.sub(r'<input([^>]*[^/])>', r'<input\1 />', html)
html = re.sub(r'<img([^>]*[^/])>', r'<img\1 />', html)
html = re.sub(r'<br([^>]*[^/])>', r'<br\1 />', html)

# Django tags
html = html.replace('{% if not user.is_authenticated %}', '{!user ? (')
html = html.replace('{% else %}', ') : (')
html = html.replace('{% endif %}', ')}')
html = html.replace('{% url \'login\' %}', '/login')
html = html.replace('{% url \'dashboard\' %}', '/dashboard')

with open('parsed_jsx.txt', 'w') as f:
    f.write(html)
