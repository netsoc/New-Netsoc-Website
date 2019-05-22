from datetime import datetime
import sys
import os
from os import path
import tempfile
import subprocess

from html2text import html2text
import markdown
import tzlocal

from .. import db
from ..models import User, BlogPost
from . import CLIError

timezone = tzlocal.get_localzone()
md = markdown.Markdown(output_format='html5')

def eprint(msg):
    print(msg, file=sys.stderr)
def pretty_authors(post):
    return ', '.join(map(lambda u: u.name, post.authors))
def pretty_time(time):
    return time.astimezone(timezone).strftime('%Y-%m-%d at %X %Z')
def find_or_make_users(users):
    obj_users = []
    for name in users:
        u = User.find_one(name)
        if not u:
            u = User(name=name)
            db.session.add(u)
        obj_users.append(u)
    db.session.commit()
    return obj_users
def get_post(id):
    post = BlogPost.find_one(id)
    if not post:
        raise CLIError(f'Post #{id} not found')
    return post
def extension(is_html):
    return '.html' if is_html else '.md'

def list(args):
    query = BlogPost.query\
            .order_by(BlogPost.edited.asc() if args.reverse else BlogPost.edited.desc())
    if args.limit != 0:
        query = query.limit(args.limit)

    for post in query:
        print(f'#{post.id}: "{post.title}" by {pretty_authors(post)} (last modified on {pretty_time(post.edited)})')

def list_simple(args):
    args.limit = 10
    args.reverse = False
    list(args)

def get(args):
    post = get_post(args.id)

    eprint(f'Title: {post.title}')
    eprint(f'Author(s): {pretty_authors(post)}')
    eprint(f'Created: on {pretty_time(post.time)}')
    if post.edited != post.time:
        eprint(f'Last edited: on {pretty_time(post.edited)}')

    if args.html:
        content = post.html
    elif post.markdown:
        content = post.markdown
    elif args.force_markdown:
        eprint('Converting HTML to Markdown...')
        content = html2text(post.html)
    else:
        eprint('Warning: Markdown unavailable, showing HTML')
        content = post.html

    print(content)

def delete(args):
    post = get_post(args.id)
    db.session.delete(post)
    db.session.commit()
    eprint(f'Post #{post.id} deleted')

def new(args):
    with tempfile.NamedTemporaryFile(mode='r', prefix='post-', suffix=extension(args.html)) as tmp_post:
        ctime = path.getmtime(tmp_post.name)
        # Open the user's editor of choice to type the contents of the post
        subprocess.call([args.editor, tmp_post.name])

        # Will only happen if the user didn't save at all
        if path.getmtime(tmp_post.name) == ctime:
            eprint('Post cancelled')
            return

        content = tmp_post.read()

    authors = find_or_make_users(args.authors)
    time = datetime.now(tz=timezone)
    post = BlogPost(
        title=args.title,
        time=time,
        edited=time,
        authors=authors,
    )

    if args.html:
        post.html = content
    else:
        post.markdown = content
        post.html = md.convert(content)

    db.session.add(post)
    db.session.commit()
    eprint(f'Created post #{post.id}')

def edit(args):
    post = get_post(args.id)

    if args.no_content:
        if not args.title and not args.authors:
            eprint(f'Not making any changes to post #{post.id}')
            return
    else:
        is_html = False
        if args.html:
            is_html = True
            content = post.html
            if post.markdown:
                # If the user wants to edit the HTML generated by existing Markdown, we don't
                # want it to get out of sync, so just clear it
                post.markdown = None
        elif post.markdown:
            content = post.markdown
        elif args.force_markdown:
            eprint('Converting HTML to Markdown...')
            content = html2text(post.html)
        else:
            is_html = True
            eprint('Warning: Markdown unavailable, editing HTML')
            content = post.html

        with tempfile.NamedTemporaryFile(mode='w+', prefix='post-', suffix=extension(is_html)) as tmp_post:
            # Write the current contents
            tmp_post.write(content)
            # Rewind to the start of the file so we can read in the modified version
            tmp_post.seek(0, os.SEEK_SET)

            ctime = path.getmtime(tmp_post.name)
            # Open the user's editor of choice to type the contents of the post
            subprocess.call([args.editor, tmp_post.name])

            # Will only happen if the user didn't save at all
            if path.getmtime(tmp_post.name) == ctime:
                eprint(f'Editing post #{post.id} cancelled')
                return

            content = tmp_post.read()

    if args.title:
        post.title = args.title
    if args.authors:
        post.authors = find_or_make_users(args.authors)

    if not args.no_content:
        if is_html:
            post.html = content
        else:
            post.markdown = content
            post.html = md.convert(content)

    db.session.add(post)
    db.session.commit()
    eprint(f'Edited post #{post.id}')
