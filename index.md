---
title: Exercises for Azure developers
permalink: index.html
layout: home
---

## Overview

The following exercises are designed to provide you with a hands-on learning experience in which you'll explore common tasks that developers perform when building and deploying solutions to Microsoft Azure.

> **Note**: To complete the exercises, you'll need an Azure subscription in which you have sufficient permissions and quota to provision the necessary Azure resources. If you don't already have one, you can sign up for an [Azure account](https://azure.microsoft.com/free).

Some exercises may have additional, or different, requirements. Those will contain a **Before you start** section specific to that exercise.

## Topic areas
{% assign exercises = site.pages | where_exp:"page", "page.url contains '/instructions'" %}
{% assign grouped_exercises = exercises | group_by: "lab.topic" %}

<ul>
{% for group in grouped_exercises %}
<li><a href="#{{ group.name | slugify }}">{{ group.name }}</a></li>
{% endfor %}
</ul>

{% for group in grouped_exercises %}

## <a id="{{ group.name | slugify }}"></a>{{ group.name }}

{% for activity in group.items %}
[{{ activity.lab.title }}]({{ site.github.url }}{{ activity.url }}) <br/> {{ activity.lab.description }} <br/> <span class="meta-grey">Level: {{activity.lab.level}} &nbsp; &nbsp; Duration: {{activity.lab.duration}} minutes</span>

---

{% endfor %}
<a href="#overview">Return to top</a>
{% endfor %}

