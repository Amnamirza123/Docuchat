create extension if not exists vector;

create table if not exists chat_sessions (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references auth.users(id) on delete cascade,
    title       text not null default 'New Chat',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index if not exists idx_chat_sessions_user on chat_sessions(user_id);

create table if not exists documents (
    id               uuid primary key default gen_random_uuid(),
    chat_session_id  uuid not null references chat_sessions(id) on delete cascade,
    user_id          uuid not null references auth.users(id) on delete cascade,
    filename         text not null,
    file_hash        text not null,
    storage_path     text not null,
    status           text not null default 'processing',
    page_count       int,
    created_at       timestamptz not null default now()
);

create index if not exists idx_documents_session on documents(chat_session_id);
create index if not exists idx_documents_hash on documents(chat_session_id, file_hash);

create table if not exists chunks (
    id               uuid primary key default gen_random_uuid(),
    document_id      uuid not null references documents(id) on delete cascade,
    chat_session_id  uuid not null references chat_sessions(id) on delete cascade,
    content          text not null,
    page_number      int,
    chunk_index      int not null,
    embedding        vector(1536),
    created_at       timestamptz not null default now()
);

create index if not exists idx_chunks_session on chunks(chat_session_id);
create index if not exists idx_chunks_embedding on chunks
    using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create table if not exists chat_messages (
    id                  uuid primary key default gen_random_uuid(),
    chat_session_id     uuid not null references chat_sessions(id) on delete cascade,
    role                text not null,
    content             text not null,
    is_grounded         boolean,
    groundedness_score  float,
    citations           jsonb,
    created_at          timestamptz not null default now()
);

create index if not exists idx_chat_messages_session on chat_messages(chat_session_id);

alter table chat_sessions enable row level security;
alter table documents enable row level security;
alter table chunks enable row level security;
alter table chat_messages enable row level security;

create policy "own sessions" on chat_sessions
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own documents" on documents
    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own chunks" on chunks
    for all using (
        chat_session_id in (select id from chat_sessions where user_id = auth.uid())
    );

create policy "own messages" on chat_messages
    for all using (
        chat_session_id in (select id from chat_sessions where user_id = auth.uid())
    );

create or replace function match_chunks(
    query_embedding vector(1536),
    session_id uuid,
    match_count int default 6
)
returns table (
    id uuid,
    document_id uuid,
    content text,
    page_number int,
    chunk_index int,
    similarity float
)
language sql stable
as $$
    select
        chunks.id,
        chunks.document_id,
        chunks.content,
        chunks.page_number,
        chunks.chunk_index,
        1 - (chunks.embedding <=> query_embedding) as similarity
    from chunks
    where chunks.chat_session_id = session_id
    order by chunks.embedding <=> query_embedding
    limit match_count;
$$;

insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do nothing;

create policy "own document files select" on storage.objects
    for select using (bucket_id = 'documents' and auth.uid()::text = (storage.foldername(name))[1]);

create policy "own document files insert" on storage.objects
    for insert with check (bucket_id = 'documents' and auth.uid()::text = (storage.foldername(name))[1]);

create policy "own document files delete" on storage.objects
    for delete using (bucket_id = 'documents' and auth.uid()::text = (storage.foldername(name))[1]);